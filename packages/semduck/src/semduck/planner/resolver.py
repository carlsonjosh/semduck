from __future__ import annotations

from dataclasses import dataclass
import re

from semduck.compiler.qualifier import (
    collect_expr_identifiers,
    contains_aggregate_function,
    qualify_expr,
    rewrite_expr_identifiers,
)
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
    ResolvedBaseExpression,
    ResolvedDerivedDimension,
    ResolvedDerivedMetric,
    ResolvedDimension,
    ResolvedMetric,
    ResolvedOrderBy,
    SemanticObject,
    SemanticTable,
    SemanticViewRegistry,
)

SIMPLE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class _MetricResolution:
    base_expressions: list[ResolvedBaseExpression]
    resolved_metrics: list[ResolvedMetric]
    reference_sql: str
    stage: str
    formula_sql: str | None = None


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
    base_expressions_by_alias: dict[str, ResolvedBaseExpression] = {}
    resolved_metrics_by_name: dict[str, ResolvedMetric] = {}
    derived_dimensions: list[ResolvedDerivedDimension] = []
    derived_metrics: list[ResolvedDerivedMetric] = []
    named_formula_metrics_by_name: dict[str, ResolvedDerivedMetric] = {}
    output_dimensions: list[str] = []
    output_metrics: list[str] = []
    output_names: set[str] = set()
    metric_resolution_cache: dict[str, _MetricResolution] = {}

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
            resolution = _resolve_metric_name(item.name, metric_index, fact_index, metric_resolution_cache)
            if resolution.stage == "base":
                raise SemanticResolutionError(f"Row-level helper metric cannot be selected directly: {item.name}")
            for base_expression in resolution.base_expressions:
                base_expressions_by_alias.setdefault(base_expression.alias, base_expression)
            for resolved in resolution.resolved_metrics:
                _add_metric_dependency(resolved_metrics_by_name, resolved)
            if resolution.formula_sql is not None:
                named_formula_metrics_by_name.setdefault(
                    item.name,
                    ResolvedDerivedMetric(alias=item.name, expr_sql=resolution.formula_sql),
                )
            _append_output(output_metrics, output_names, item.name)
            continue

        if isinstance(item, DerivedMetric):
            refs = _resolve_metric_expression_refs(item.expr, metric_index, fact_index)
            fact_refs = [name for name in refs if name in fact_index]
            base_metric_refs: list[str] = []
            aggregate_metric_refs: list[str] = []
            for ref_name in refs:
                if ref_name not in metric_index:
                    continue
                resolution = _resolve_metric_name(ref_name, metric_index, fact_index, metric_resolution_cache)
                if resolution.stage == "base":
                    base_metric_refs.append(ref_name)
                else:
                    aggregate_metric_refs.append(ref_name)

            if (fact_refs or base_metric_refs) and (
                parsed.dimensions or parsed_metrics_have_named_metric or aggregate_metric_refs
            ):
                raise SemanticResolutionError(
                    f"Derived metric expression cannot mix row-level references with grouped or metric-based queries: {item.alias}"
                )
            replacements = {}
            for ref_name in refs:
                if ref_name in metric_index:
                    resolution = _resolve_metric_name(ref_name, metric_index, fact_index, metric_resolution_cache)
                    for base_expression in resolution.base_expressions:
                        base_expressions_by_alias.setdefault(base_expression.alias, base_expression)
                    for resolved in resolution.resolved_metrics:
                        _add_metric_dependency(resolved_metrics_by_name, resolved)
                    replacements[ref_name] = resolution.reference_sql
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
    base_expressions = list(base_expressions_by_alias.values())
    resolved_metrics = list(resolved_metrics_by_name.values())
    for name in output_metrics:
        derived = named_formula_metrics_by_name.get(name)
        if derived is not None:
            derived_metrics.append(derived)

    anchor_table = choose_anchor_table(resolved_dimensions, resolved_metrics, registry)
    required_joins = resolve_required_joins(anchor_table, resolved_dimensions, resolved_metrics, registry)

    rewritten_where = None
    if parsed.where_clause:
        rewritten_where = rewrite_where_clause(parsed.where_clause, registry)

    resolved_order_by = _resolve_order_by(parsed, output_dimensions, output_metrics)

    return QueryPlan(
        semantic_view_ref=parsed.semantic_view_ref,
        from_table=anchor_table.name,
        from_alias=anchor_table.alias,
        joins=required_joins,
        dimensions=resolved_dimensions,
        base_expressions=base_expressions,
        metrics=resolved_metrics,
        derived_dimensions=derived_dimensions,
        derived_metrics=derived_metrics,
        output_dimensions=output_dimensions,
        output_metrics=output_metrics,
        where_clause=rewritten_where,
        order_by=resolved_order_by,
        limit=parsed.limit,
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
    fact_index: dict[str, tuple[SemanticTable, SemanticObject]],
    metric_resolution_cache: dict[str, _MetricResolution],
    stack: tuple[str, ...] = (),
) -> _MetricResolution:
    if metric_name not in metric_index:
        raise SemanticResolutionError(f"Unknown metric: {metric_name}")
    if metric_name in metric_resolution_cache:
        return metric_resolution_cache[metric_name]
    if metric_name in stack:
        cycle = " -> ".join((*stack, metric_name))
        raise SemanticResolutionError(f"Cyclic metric definition: {cycle}")

    table, metric = metric_index[metric_name]
    refs = collect_expr_identifiers(metric.expr)
    local_metric_refs = [name for name in refs if name in table.metrics]
    local_fact_refs = [name for name in refs if name in table.facts]
    physical_refs = [name for name in refs if name not in table.metrics and name not in table.facts]
    cross_table_metric_refs = [
        name for name in refs if name in metric_index and name not in table.metrics and metric_index[name][0].name != table.name
    ]
    cross_table_fact_refs = [
        name for name in refs if name in fact_index and name not in table.facts and fact_index[name][0].name != table.name
    ]
    if cross_table_metric_refs or cross_table_fact_refs:
        names = sorted(set(cross_table_metric_refs + cross_table_fact_refs))
        raise SemanticResolutionError(
            f"Metric definition cannot reference semantic objects from another table: {metric_name} -> {', '.join(names)}"
        )

    resolved_metrics_by_name: dict[str, ResolvedMetric] = {}
    base_expressions_by_alias: dict[str, ResolvedBaseExpression] = {}
    metric_aliases: dict[str, str] = {}
    aggregate_metric_refs: list[str] = []
    for ref_name in local_metric_refs:
        resolution = _resolve_metric_name(
            ref_name,
            metric_index,
            fact_index,
            metric_resolution_cache,
            (*stack, metric_name),
        )
        for base_expression in resolution.base_expressions:
            base_expressions_by_alias.setdefault(base_expression.alias, base_expression)
        for resolved in resolution.resolved_metrics:
            resolved_metrics_by_name.setdefault(resolved.request_name, resolved)
        if resolution.stage == "base":
            metric_aliases[ref_name] = resolution.reference_sql
        else:
            aggregate_metric_refs.append(ref_name)

    aggregate_expr = contains_aggregate_function(metric.expr)

    if aggregate_expr:
        if aggregate_metric_refs:
            raise SemanticResolutionError(
                f"Aggregate metric cannot reference aggregate metrics: {metric_name} -> {', '.join(sorted(aggregate_metric_refs))}"
            )
        for ref_name in local_fact_refs:
            base_expressions_by_alias.setdefault(ref_name, _fact_base_expression(table.facts[ref_name], table.alias))
        known_aliases = {name: name for name in local_fact_refs}
        known_aliases.update(metric_aliases)
        for ref_name in physical_refs:
            alias = f"{metric_name}__{ref_name}"
            base_expressions_by_alias.setdefault(
                alias,
                ResolvedBaseExpression(alias=alias, expr_sql=qualify_expr(ref_name, table.alias)),
            )
            known_aliases[ref_name] = alias
        aggregate_expr_sql = rewrite_expr_identifiers(metric.expr, known_aliases)
        resolution = _MetricResolution(
            base_expressions=list(base_expressions_by_alias.values()),
            resolved_metrics=[
                *list(resolved_metrics_by_name.values()),
                ResolvedMetric(
                    request_name=metric_name,
                    table_name=table.name,
                    alias=table.alias,
                    expr_sql=aggregate_expr_sql,
                ),
            ],
            reference_sql=metric_name,
            stage="aggregate",
        )
        metric_resolution_cache[metric_name] = resolution
        return resolution

    if aggregate_metric_refs and (local_fact_refs or physical_refs or metric_aliases):
        resolution = _MetricResolution(
            base_expressions=[],
            resolved_metrics=[],
            reference_sql="",
            stage="invalid",
        )
        raise SemanticResolutionError(
            f"Formula metric cannot mix aggregate metrics with row-level expressions: {metric_name}"
        )

    if aggregate_metric_refs:
        replacements = {
            ref_name: _parenthesized_reference(_resolve_metric_name(
                ref_name,
                metric_index,
                fact_index,
                metric_resolution_cache,
                (*stack, metric_name),
            ).reference_sql)
            for ref_name in aggregate_metric_refs
        }
        rewritten_expr = rewrite_expr_identifiers(metric.expr, replacements)
        resolution = _MetricResolution(
            base_expressions=list(base_expressions_by_alias.values()),
            resolved_metrics=list(resolved_metrics_by_name.values()),
            reference_sql=_parenthesized_reference(rewritten_expr),
            stage="aggregate",
            formula_sql=rewritten_expr,
        )
    else:
        alias_replacements = {name: name for name in local_fact_refs}
        alias_replacements.update(metric_aliases)
        for ref_name in local_fact_refs:
            base_expressions_by_alias.setdefault(ref_name, _fact_base_expression(table.facts[ref_name], table.alias))

        input_alias = f"{metric_name}__input"
        rewritten_expr = _qualify_base_stage_expr(metric.expr, table, alias_replacements)
        base_expressions_by_alias[input_alias] = ResolvedBaseExpression(
            alias=input_alias,
            expr_sql=rewritten_expr,
        )
        resolution = _MetricResolution(
            base_expressions=list(base_expressions_by_alias.values()),
            resolved_metrics=[],
            reference_sql=input_alias,
            stage="base",
        )
    metric_resolution_cache[metric_name] = resolution
    return resolution


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


def _inline_fact_expr(fact: SemanticObject, alias: str) -> str:
    expr_sql = qualify_expr(fact.expr, alias)
    if SIMPLE_IDENTIFIER_RE.match(fact.expr.strip()):
        return expr_sql
    return f"({expr_sql})"


def _fact_base_expression(fact: SemanticObject, alias: str) -> ResolvedBaseExpression:
    return ResolvedBaseExpression(alias=fact.name, expr_sql=qualify_expr(fact.expr, alias))


def _qualify_base_stage_expr(expr: str, table: SemanticTable, alias_replacements: dict[str, str]) -> str:

    class _BaseStageDict(dict):
        def __contains__(self, key):  # type: ignore[override]
            return True

        def __getitem__(self, key):  # type: ignore[override]
            if key in alias_replacements:
                return alias_replacements[key]
            return f"{table.alias}.{key}"

    return rewrite_expr_identifiers(expr, _BaseStageDict())


def _parenthesized_reference(expr: str) -> str:
    return f"({expr})"


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


def _resolve_order_by(
    parsed: ParsedSemanticRequest,
    output_dimensions: list[str],
    output_metrics: list[str],
) -> list[ResolvedOrderBy]:
    valid_names = set(output_dimensions) | set(output_metrics)
    resolved: list[ResolvedOrderBy] = []
    for item in parsed.order_by:
        if item.name not in valid_names:
            raise SemanticResolutionError(
                f"ORDER BY can only reference selected outputs: {item.name}"
            )
        resolved.append(ResolvedOrderBy(name=item.name, descending=item.descending))
    return resolved
