from __future__ import annotations

from collections import deque
import re

from semduck.errors import SemanticJoinError
from semduck.types import ResolvedDimension, ResolvedMetric, SemanticJoin, SemanticTable, SemanticViewRegistry

JOIN_EQ_RE = re.compile(
    r"(LEFT_TABLE|RIGHT_TABLE)\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"(LEFT_TABLE|RIGHT_TABLE)\.([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


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

    resolved_joins: list[SemanticJoin] = []
    seen_join_keys: set[tuple[str, str, str]] = set()
    reached_tables = {anchor_table.name}

    for table_name in sorted(required_tables):
        if table_name in reached_tables:
            continue
        path = _find_join_path(
            start_tables=reached_tables,
            target_table=table_name,
            registry=registry,
            require_safe=True,
        )
        if path is None:
            unsafe_path = _find_join_path(
                start_tables=reached_tables,
                target_table=table_name,
                registry=registry,
                require_safe=False,
            )
            if unsafe_path is not None:
                raise SemanticJoinError(
                    f"No grain-safe join path found between {anchor_table.name} and {table_name}"
                )
            raise SemanticJoinError(
                f"No join path found between {anchor_table.name} and {table_name}"
            )

        for join in path:
            join_key = (join.left_table, join.right_table, join.join_expr)
            if join_key in seen_join_keys:
                continue
            resolved_joins.append(join)
            seen_join_keys.add(join_key)
            reached_tables.add(join.left_table)
            reached_tables.add(join.right_table)

    return resolved_joins


def _find_join_path(
    *,
    start_tables: set[str],
    target_table: str,
    registry: SemanticViewRegistry,
    require_safe: bool,
) -> list[SemanticJoin] | None:
    queue: deque[tuple[str, list[SemanticJoin]]] = deque((table_name, []) for table_name in sorted(start_tables))
    visited: set[str] = set(start_tables)

    while queue:
        current_table, path = queue.popleft()
        if current_table == target_table:
            return path

        for join in registry.joins:
            neighbor = _neighbor_for_join(join, current_table)
            if neighbor is None or neighbor in visited:
                continue
            if require_safe and not _is_grain_safe_hop(current_table, join, registry):
                continue
            visited.add(neighbor)
            queue.append((neighbor, [*path, join]))

    return None


def _neighbor_for_join(join: SemanticJoin, table_name: str) -> str | None:
    if join.left_table == table_name:
        return join.right_table
    if join.right_table == table_name:
        return join.left_table
    return None


def _is_grain_safe_hop(
    current_table: str,
    join: SemanticJoin,
    registry: SemanticViewRegistry,
) -> bool:
    if join.left_table == current_table:
        target_table = registry.tables[join.right_table]
        target_side = "RIGHT_TABLE"
    elif join.right_table == current_table:
        target_table = registry.tables[join.left_table]
        target_side = "LEFT_TABLE"
    else:
        return False

    if not target_table.primary_key_columns:
        return False

    target_columns = {
        column
        for side, column in _extract_join_columns(join.join_expr)
        if side == target_side
    }
    return target_columns == set(target_table.primary_key_columns)


def _extract_join_columns(join_expr: str) -> list[tuple[str, str]]:
    columns: list[tuple[str, str]] = []
    for left_side, left_column, right_side, right_column in JOIN_EQ_RE.findall(join_expr):
        columns.append((left_side.upper(), left_column))
        columns.append((right_side.upper(), right_column))
    return columns
