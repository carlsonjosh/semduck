from __future__ import annotations

import json
from typing import Any

from duckdb_semantic.authoring.validators import build_table_alias
from duckdb_semantic.errors import SemanticRegistryError
from duckdb_semantic.types import LoadResult


def _primary_key_columns(table_spec: dict[str, Any]) -> str | None:
    primary_key = table_spec.get("primary_key") or {}
    columns = primary_key.get("columns") or []
    return json.dumps(columns) if columns else None


def _delete_existing(conn: Any, view_name: str) -> None:
    for table_name in (
        "semantic.joins",
        "semantic.metrics",
        "semantic.facts",
        "semantic.dimensions",
        "semantic.semantic_view_tables",
        "semantic.semantic_views",
    ):
        conn.execute(f"delete from {table_name} where view_name = ?", [view_name])


def write_semantic_view(
    conn: Any,
    spec: dict[str, Any],
    *,
    source_yaml: str,
    replace_existing: bool = True,
    validate_only: bool = False,
) -> LoadResult:
    view_name = spec["name"]
    if validate_only:
        return LoadResult(ok=True, view_name=view_name, validated_only=True)

    description = spec.get("description")
    used_aliases: set[str] = set()
    conn.execute("begin transaction")
    try:
        if replace_existing:
            _delete_existing(conn, view_name)

        conn.execute(
            """
            insert into semantic.semantic_views (view_name, description, source_yaml)
            values (?, ?, ?)
            """,
            [view_name, description, source_yaml],
        )

        for table_spec in spec.get("tables", []):
            table_name = table_spec["name"]
            base_table = table_spec["base_table"]
            table_alias = build_table_alias(table_name, used_aliases)
            conn.execute(
                """
                insert into semantic.semantic_view_tables (
                    view_name, table_name, physical_schema, physical_table, table_alias,
                    primary_key_columns, description
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    view_name,
                    table_name,
                    base_table.get("schema"),
                    base_table["table"],
                    table_alias,
                    _primary_key_columns(table_spec),
                    table_spec.get("description"),
                ],
            )

            for dimension in table_spec.get("dimensions", []):
                conn.execute(
                    """
                    insert into semantic.dimensions (
                        view_name, table_name, dimension_name, dimension_kind, expr, data_type, description
                    ) values (?, ?, ?, 'dimension', ?, ?, ?)
                    """,
                    [
                        view_name,
                        table_name,
                        dimension["name"],
                        dimension["expr"],
                        dimension.get("data_type"),
                        dimension.get("description"),
                    ],
                )

            for dimension in table_spec.get("time_dimensions", []):
                conn.execute(
                    """
                    insert into semantic.dimensions (
                        view_name, table_name, dimension_name, dimension_kind, expr, data_type, description
                    ) values (?, ?, ?, 'time_dimension', ?, ?, ?)
                    """,
                    [
                        view_name,
                        table_name,
                        dimension["name"],
                        dimension["expr"],
                        dimension.get("data_type"),
                        dimension.get("description"),
                    ],
                )

            for fact in table_spec.get("facts", []):
                conn.execute(
                    """
                    insert into semantic.facts (
                        view_name, table_name, fact_name, expr, data_type, description
                    ) values (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        view_name,
                        table_name,
                        fact["name"],
                        fact["expr"],
                        fact.get("data_type"),
                        fact.get("description"),
                    ],
                )

            for metric in table_spec.get("metrics", []):
                conn.execute(
                    """
                    insert into semantic.metrics (
                        view_name, table_name, metric_name, metric_type, expr, default_agg, description
                    ) values (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        view_name,
                        table_name,
                        metric["name"],
                        metric["metric_type"],
                        metric["expr"],
                        metric.get("default_agg"),
                        metric.get("description"),
                    ],
                )

        for join in spec.get("joins", []):
            conn.execute(
                """
                insert into semantic.joins (
                    view_name, join_name, left_table, right_table, join_type, join_expr, description
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    view_name,
                    join["name"],
                    join["left_table"],
                    join["right_table"],
                    join["join_type"],
                    join["join_expr"],
                    join.get("description"),
                ],
            )

        conn.execute("commit")
        return LoadResult(ok=True, view_name=view_name, validated_only=False)
    except Exception as exc:
        conn.execute("rollback")
        if isinstance(exc, SemanticRegistryError):
            raise
        raise SemanticRegistryError(str(exc)) from exc

