from __future__ import annotations

from semduck.compiler.qualifier import collect_expr_identifiers, qualify_expr, qualify_metric_expr, rewrite_expr_identifiers
from semduck.errors import SemanticResolutionError
from semduck.planner.joins import choose_anchor_table, resolve_required_joins
from semduck.planner.where_rewriter import rewrite_where_clause
from semduck.types import (
    DerivedDimension,
    DerivedMetric,
    NamedDimension,
    NamedMetric,
    ParsedSemanticRequest,
    QueryPlan,
    ResolvedDerivedDimension,
    ResolvedDerivedMetric,
    ResolvedDimension,
    ResolvedMetric,
    SemanticObject,
    SemanticTable,
    SemanticViewRegistry,
)


def _build_indexes(
    registry: SemanticViewRegistry,
) -> tuple[
    dict[str, tuple[SemanticTable, SemanticObject]],
    dict[str, tuple[SemanticTable, SemanticObject]],
    dict[str, tuple[SemanticTable, SemanticObject]],
]:
    dim_index: dict[str, tuple[SemanticTable, SemanticObject]] = {}
    fact_index: dict[str, tuple[SemanticTable, SemanticObject]] = {}
    metric_index: dict[str, tuple[SemanticTable, SemanticObject]] = {}
    ambiguous_dimensions = set()
    ambiguous_facts = set()
    ambiguous_metrics = set()

    for table in registry.tables.values():
        for dim_name, dim in table.dimensions.items():
            if dim_name in dim_index:
                ambiguous_dimensions.add(dim_name)
            else:
                dim_index[dim_name] = (table, dim)

        for fact_name, fact in table.facts.items():
            if fact_name in fact_index:
                ambiguous_facts.add(fact_name)
            else:
                fact_index[fact_name] = (table, fact)

        for metric_name, metric in table.metrics.items():
            if metric_name in metric_index:
                ambiguous_metrics.add(metric_name)
            else:
                metric_index[metric_name] = (table, metric)

    for name in ambiguous_dimensions:
        dim_index.pop(name, None)
    for name in ambiguous_facts:
        fact_index.pop(name, None)
    for name in ambiguous_metrics:
        metric_index.pop(name, None)

    return dim_index, fact_index, metric_index


def build_query_plan(parsed: ParsedSemanticRequest, registry: SemanticViewRegistry) -> QueryPlan:
    dim_index, fact_index, metric_index = _build_indexes(registry)
    resolved_dimensions_by_name: dict[str, ResolvedDimension] = {}
    resolved_metrics_by_name: dict[str, ResolvedMetric] = {}
    derived_dimensions: list[ResolvedDerivedDimension] = []
    derived_metrics: list[ResolvedDerivedMetric] = []
    output_dimensions: list[str] = []
    output_metrics: list[str] = []
    output_names: set[str] = set()

    parsed_metrics_have_named_metric = any(isinstance(item, NamedMetric) for item in parsed.metrics)

    for item in parsed.dimensions:
        if isinstance(item, NamedDimension):
            resolved = _resolve_dimension_name(item.name, dim_index)
            _add_dimension_dependency(resolved_dimensions_by_name, resolved)
            _append_output(output_dimensions, output_names, item.name)
            continue

        if isinstance(item, DerivedDimension):
            refs = _resolve_dimension_expression_refs(item.expr, dim_index, fact_index)
            if any(name in fact_index for name in refs) and parsed.metrics:
                raise SemanticResolutionError(
                    f"Derived dimension expression cannot reference facts when metrics are selected: {item.alias}"
                )
            replacements = {}
            for ref_name in refs:
                if ref_name in dim_index:
                    resolved = _resolve_dimension_name(ref_name, dim_index)
                else:
                    resolved = _resolve_fact_name(ref_name, fact_index)
                _add_dimension_dependency(resolved_dimensions_by_name, resolved)
                replacements[ref_name] = resolved.request_name
            try:
                expr_sql = rewrite_expr_identifiers(
                    item.expr,
                    replacements,
                    unknown_error="Unknown identifier in derived dimension expression: {name}",
                )
            except ValueError as exc:
                raise SemanticResolutionError(str(exc)) from exc
            derived_dimensions.append(ResolvedDerivedDimension(alias=item.alias, expr_sql=expr_sql))
            _append_output(output_dimensions, output_names, item.alias)

    for item in parsed.metrics:
        if isinstance(item, NamedMetric):
            resolved = _resolve_metric_name(item.name, metric_index)
            _add_metric_dependency(resolved_metrics_by_name, resolved)
            _append_output(output_metrics, output_names, item.name)
            continue

        if isinstance(item, DerivedMetric):
            refs = _resolve_metric_expression_refs(item.expr, metric_index, fact_index)
            fact_refs = [name for name in refs if name in fact_index]
            metric_refs = [name for name in refs if name in metric_index]
            if fact_refs and (parsed.dimensions or parsed_metrics_have_named_metric or metric_refs):
                raise SemanticResolutionError(
                    f"Derived metric expression cannot mix facts with grouped or metric-based queries: {item.alias}"
                )
            replacements = {}
            for ref_name in refs:
                if ref_name in metric_index:
                    resolved = _resolve_metric_name(ref_name, metric_index)
                    _add_metric_dependency(resolved_metrics_by_name, resolved)
                    replacements[ref_name] = resolved.request_name
                else:
                    resolved = _resolve_fact_name(ref_name, fact_index)
                    _add_dimension_dependency(resolved_dimensions_by_name, resolved)
                    replacements[ref_name] = resolved.request_name
            try:
                expr_sql = rewrite_expr_identifiers(
                    item.expr,
                    replacements,
                    unknown_error="Unknown identifier in derived metric expression: {name}",
                )
            except ValueError as exc:
                raise SemanticResolutionError(str(exc)) from exc
            derived_metrics.append(ResolvedDerivedMetric(alias=item.alias, expr_sql=expr_sql))
            _append_output(output_metrics, output_names, item.alias)

    resolved_dimensions = list(resolved_dimensions_by_name.values())
    resolved_metrics = list(resolved_metrics_by_name.values())

    anchor_table = choose_anchor_table(resolved_dimensions, resolved_metrics, registry)
    required_joins = resolve_required_joins(anchor_table, resolved_dimensions, resolved_metrics, registry)

    rewritten_where = None
    if parsed.where_clause:
        rewritten_where = rewrite_where_clause(parsed.where_clause, registry)

    return QueryPlan(
        semantic_view_ref=parsed.semantic_view_ref,
        from_table=anchor_table.name,
        from_alias=anchor_table.alias,
        joins=required_joins,
        dimensions=resolved_dimensions,
        metrics=resolved_metrics,
        derived_dimensions=derived_dimensions,
        derived_metrics=derived_metrics,
        output_dimensions=output_dimensions,
        output_metrics=output_metrics,
        where_clause=rewritten_where,
    )


def _resolve_dimension_name(
    dim_name: str,
    dim_index: dict[str, tuple[SemanticTable, SemanticObject]],
) -> ResolvedDimension:
    if dim_name not in dim_index:
        raise SemanticResolutionError(f"Unknown dimension: {dim_name}")
    table, dim = dim_index[dim_name]
    return ResolvedDimension(
        request_name=dim_name,
        table_name=table.name,
        alias=table.alias,
        expr_sql=qualify_expr(dim.expr, table.alias),
        object_type=dim.object_type,
    )


def _resolve_fact_name(
    fact_name: str,
    fact_index: dict[str, tuple[SemanticTable, SemanticObject]],
) -> ResolvedDimension:
    if fact_name not in fact_index:
        raise SemanticResolutionError(f"Unknown fact: {fact_name}")
    table, fact = fact_index[fact_name]
    return ResolvedDimension(
        request_name=fact_name,
        table_name=table.name,
        alias=table.alias,
        expr_sql=qualify_expr(fact.expr, table.alias),
        object_type=fact.object_type,
    )


def _resolve_metric_name(
    metric_name: str,
    metric_index: dict[str, tuple[SemanticTable, SemanticObject]],
) -> ResolvedMetric:
    if metric_name not in metric_index:
        raise SemanticResolutionError(f"Unknown metric: {metric_name}")
    table, metric = metric_index[metric_name]
    return ResolvedMetric(
        request_name=metric_name,
        table_name=table.name,
        alias=table.alias,
        expr_sql=qualify_metric_expr(metric, table.alias),
        metric_type=metric.metric_type or "unknown",
    )


def _resolve_dimension_expression_refs(
    expr: str,
    dim_index: dict[str, tuple[SemanticTable, SemanticObject]],
    fact_index: dict[str, tuple[SemanticTable, SemanticObject]],
) -> list[str]:
    refs = collect_expr_identifiers(expr)
    resolved: list[str] = []
    for ref in refs:
        if ref in dim_index or ref in fact_index:
            resolved.append(ref)
            continue
        raise SemanticResolutionError(f"Unknown identifier in derived dimension expression: {ref}")
    return resolved


def _resolve_metric_expression_refs(
    expr: str,
    metric_index: dict[str, tuple[SemanticTable, SemanticObject]],
    fact_index: dict[str, tuple[SemanticTable, SemanticObject]],
) -> list[str]:
    refs = collect_expr_identifiers(expr)
    resolved: list[str] = []
    for ref in refs:
        if ref in metric_index or ref in fact_index:
            resolved.append(ref)
            continue
        raise SemanticResolutionError(f"Unknown identifier in derived metric expression: {ref}")
    return resolved


def _add_dimension_dependency(
    resolved_dimensions: dict[str, ResolvedDimension],
    resolved: ResolvedDimension,
) -> None:
    resolved_dimensions.setdefault(resolved.request_name, resolved)


def _add_metric_dependency(
    resolved_metrics: dict[str, ResolvedMetric],
    resolved: ResolvedMetric,
) -> None:
    resolved_metrics.setdefault(resolved.request_name, resolved)


def _append_output(outputs: list[str], seen: set[str], name: str) -> None:
    if name in seen:
        raise SemanticResolutionError(f"Duplicate output alias in semantic request: {name}")
    seen.add(name)
    outputs.append(name)
