from __future__ import annotations

from typing import Any

from semduck.errors import SemanticRegistryError
from semduck.types import SemanticJoin, SemanticObject, SemanticTable, SemanticViewRegistry


def load_semantic_view_registry(conn: Any, semantic_view_ref: str) -> SemanticViewRegistry:
    view_row = conn.execute(
        """
        select view_name
        from semantic.semantic_views
        where view_name = ?
        """,
        [semantic_view_ref],
    ).fetchone()
    if not view_row:
        raise SemanticRegistryError(f"Unknown semantic view: {semantic_view_ref}")

    table_rows = conn.execute(
        """
        select table_name, physical_schema, physical_table, table_alias
        from semantic.semantic_view_tables
        where view_name = ?
        order by table_name
        """,
        [semantic_view_ref],
    ).fetchall()

    tables: dict[str, SemanticTable] = {}
    for table_name, physical_schema, physical_table, table_alias in table_rows:
        dim_rows = conn.execute(
            """
            select dimension_name, dimension_kind, expr, data_type
            from semantic.dimensions
            where view_name = ? and table_name = ?
            """,
            [semantic_view_ref, table_name],
        ).fetchall()
        fact_rows = conn.execute(
            """
            select fact_name, expr, data_type
            from semantic.facts
            where view_name = ? and table_name = ?
            """,
            [semantic_view_ref, table_name],
        ).fetchall()
        metric_rows = conn.execute(
            """
            select metric_name, metric_type, expr, default_agg
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
            )
            for name, kind, expr, data_type in dim_rows
        }
        facts = {
            name: SemanticObject(
                name=name,
                object_type="fact",
                expr=expr,
                data_type=data_type,
                table_name=table_name,
            )
            for name, expr, data_type in fact_rows
        }
        metrics = {
            name: SemanticObject(
                name=name,
                object_type="metric",
                expr=expr,
                metric_type=metric_type,
                default_agg=default_agg,
                table_name=table_name,
            )
            for name, metric_type, expr, default_agg in metric_rows
        }
        tables[table_name] = SemanticTable(
            name=table_name,
            physical_schema=physical_schema,
            physical_table=physical_table,
            alias=table_alias,
            dimensions=dimensions,
            metrics=metrics,
            facts=facts,
        )

    join_rows = conn.execute(
        """
        select left_table, right_table, join_type, join_expr
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
        )
        for left_table, right_table, join_type, join_expr in join_rows
    ]

    return SemanticViewRegistry(view_name=semantic_view_ref, tables=tables, joins=joins)
