from __future__ import annotations

from duckdb_semantic.compiler.qualifier import qualify_expr, qualify_metric_expr
from duckdb_semantic.errors import SemanticResolutionError
from duckdb_semantic.planner.joins import choose_anchor_table, resolve_required_joins
from duckdb_semantic.planner.where_rewriter import rewrite_where_clause
from duckdb_semantic.types import (
    ParsedSemanticRequest,
    QueryPlan,
    ResolvedDimension,
    ResolvedMetric,
    SemanticObject,
    SemanticTable,
    SemanticViewRegistry,
)


def _build_indexes(registry: SemanticViewRegistry) -> tuple[dict[str, tuple[SemanticTable, SemanticObject]], dict[str, tuple[SemanticTable, SemanticObject]]]:
    dim_index = {}
    metric_index = {}
    ambiguous_dimensions = set()
    ambiguous_metrics = set()

    for table in registry.tables.values():
        for dim_name, dim in table.dimensions.items():
            if dim_name in dim_index:
                ambiguous_dimensions.add(dim_name)
            else:
                dim_index[dim_name] = (table, dim)

        for metric_name, metric in table.metrics.items():
            if metric_name in metric_index:
                ambiguous_metrics.add(metric_name)
            else:
                metric_index[metric_name] = (table, metric)

    for name in ambiguous_dimensions:
        dim_index.pop(name, None)
    for name in ambiguous_metrics:
        metric_index.pop(name, None)

    return dim_index, metric_index


def build_query_plan(parsed: ParsedSemanticRequest, registry: SemanticViewRegistry) -> QueryPlan:
    dim_index, metric_index = _build_indexes(registry)
    resolved_dimensions: list[ResolvedDimension] = []
    resolved_metrics: list[ResolvedMetric] = []

    for dim_name in parsed.dimensions:
        if dim_name not in dim_index:
            all_matches = [table.name for table in registry.tables.values() if dim_name in table.dimensions]
            if len(all_matches) > 1:
                raise SemanticResolutionError(f"Ambiguous dimension name: {dim_name}")
            raise SemanticResolutionError(f"Unknown dimension: {dim_name}")
        table, dim = dim_index[dim_name]
        resolved_dimensions.append(
            ResolvedDimension(
                request_name=dim_name,
                table_name=table.name,
                alias=table.alias,
                expr_sql=qualify_expr(dim.expr, table.alias),
                object_type=dim.object_type,
            )
        )

    for metric_name in parsed.metrics:
        if metric_name not in metric_index:
            all_matches = [table.name for table in registry.tables.values() if metric_name in table.metrics]
            if len(all_matches) > 1:
                raise SemanticResolutionError(f"Ambiguous metric name: {metric_name}")
            raise SemanticResolutionError(f"Unknown metric: {metric_name}")
        table, metric = metric_index[metric_name]
        resolved_metrics.append(
            ResolvedMetric(
                request_name=metric_name,
                table_name=table.name,
                alias=table.alias,
                expr_sql=qualify_metric_expr(metric, table.alias),
                metric_type=metric.metric_type or "unknown",
            )
        )

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
        where_clause=rewritten_where,
    )

