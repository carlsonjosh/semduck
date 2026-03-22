from __future__ import annotations

from semduck.errors import SemanticJoinError
from semduck.types import ResolvedDimension, ResolvedMetric, SemanticJoin, SemanticTable, SemanticViewRegistry


def choose_anchor_table(
    resolved_dimensions: list[ResolvedDimension],
    resolved_metrics: list[ResolvedMetric],
    registry: SemanticViewRegistry,
) -> SemanticTable:
    if resolved_metrics:
        return registry.tables[resolved_metrics[0].table_name]
    if resolved_dimensions:
        return registry.tables[resolved_dimensions[0].table_name]
    return next(iter(registry.tables.values()))


def resolve_required_joins(
    anchor_table: SemanticTable,
    resolved_dimensions: list[ResolvedDimension],
    resolved_metrics: list[ResolvedMetric],
    registry: SemanticViewRegistry,
) -> list[SemanticJoin]:
    required_tables = {anchor_table.name}
    required_tables.update(item.table_name for item in resolved_dimensions)
    required_tables.update(item.table_name for item in resolved_metrics)

    if len(required_tables) == 1:
        return []

    joins = []
    for table_name in sorted(required_tables):
        if table_name == anchor_table.name:
            continue
        match = None
        for join in registry.joins:
            if {join.left_table, join.right_table} == {anchor_table.name, table_name}:
                match = join
                break
        if not match:
            raise SemanticJoinError(
                f"No direct join found between {anchor_table.name} and {table_name}"
            )
        joins.append(match)

    return joins
