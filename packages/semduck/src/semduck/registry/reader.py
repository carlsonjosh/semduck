from __future__ import annotations

import json
from typing import Any

from semduck.errors import SemanticRegistryError
from semduck.types import SemanticJoin, SemanticObject, SemanticTable, SemanticViewRegistry


def _load_json_text(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else None


def load_semantic_view_registry(conn: Any, semantic_view_ref: str) -> SemanticViewRegistry:
    view_row = conn.execute(
        """
        select view_name, ai_context
        from semantic.semantic_views
        where view_name = ?
        """,
        [semantic_view_ref],
    ).fetchone()
    if not view_row:
        raise SemanticRegistryError(f"Unknown semantic view: {semantic_view_ref}")
    _, view_ai_context = view_row

    table_rows = conn.execute(
        """
        select table_name, physical_schema, physical_table, table_alias, primary_key_columns, ai_context
        from semantic.semantic_view_tables
        where view_name = ?
        order by table_name
        """,
        [semantic_view_ref],
    ).fetchall()

    tables: dict[str, SemanticTable] = {}
    for table_name, physical_schema, physical_table, table_alias, primary_key_columns, table_ai_context in table_rows:
        dim_rows = conn.execute(
            """
            select dimension_name, dimension_kind, expr, data_type, ai_context
            from semantic.dimensions
            where view_name = ? and table_name = ?
            """,
            [semantic_view_ref, table_name],
        ).fetchall()
        fact_rows = conn.execute(
            """
            select fact_name, expr, data_type, ai_context
            from semantic.facts
            where view_name = ? and table_name = ?
            """,
            [semantic_view_ref, table_name],
        ).fetchall()
        metric_rows = conn.execute(
            """
            select metric_name, expr, ai_context
            from semantic.metrics
            where view_name = ? and table_name = ?
            """,
            [semantic_view_ref, table_name],
        ).fetchall()

        dimensions = {
            name: SemanticObject(
                name=name,
                object_type=kind,
                expr=expr,
                data_type=data_type,
                table_name=table_name,
                ai_context=_load_json_text(ai_context),
            )
            for name, kind, expr, data_type, ai_context in dim_rows
        }
        facts = {
            name: SemanticObject(
                name=name,
                object_type="fact",
                expr=expr,
                data_type=data_type,
                table_name=table_name,
                ai_context=_load_json_text(ai_context),
            )
            for name, expr, data_type, ai_context in fact_rows
        }
        metrics = {
            name: SemanticObject(
                name=name,
                object_type="metric",
                expr=expr,
                table_name=table_name,
                ai_context=_load_json_text(ai_context),
            )
            for name, expr, ai_context in metric_rows
        }
        tables[table_name] = SemanticTable(
            name=table_name,
            physical_schema=physical_schema,
            physical_table=physical_table,
            alias=table_alias,
            primary_key_columns=list(json.loads(primary_key_columns)) if primary_key_columns else [],
            dimensions=dimensions,
            metrics=metrics,
            facts=facts,
            ai_context=_load_json_text(table_ai_context),
        )

    join_rows = conn.execute(
        """
        select left_table, right_table, join_type, join_expr, ai_context
        from semantic.joins
        where view_name = ?
        order by left_table, right_table
        """,
        [semantic_view_ref],
    ).fetchall()
    joins = [
        SemanticJoin(
            left_table=left_table,
            right_table=right_table,
            join_type=join_type,
            join_expr=join_expr,
            ai_context=_load_json_text(ai_context),
        )
        for left_table, right_table, join_type, join_expr, ai_context in join_rows
    ]

    return SemanticViewRegistry(
        view_name=semantic_view_ref,
        tables=tables,
        joins=joins,
        ai_context=_load_json_text(view_ai_context),
    )
