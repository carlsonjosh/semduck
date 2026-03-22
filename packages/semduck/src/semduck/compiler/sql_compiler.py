from __future__ import annotations

from semduck.types import QueryPlan, SemanticViewRegistry


def fully_qualified_table(physical_schema: str | None, physical_table: str) -> str:
    if physical_schema:
        return f"{physical_schema}.{physical_table}"
    return physical_table


def compile_sql(plan: QueryPlan, registry: SemanticViewRegistry) -> str:
    select_parts = []
    group_by_positions = []
    position = 1

    for dimension in plan.dimensions:
        select_parts.append(f"{dimension.expr_sql} as {dimension.request_name}")
        group_by_positions.append(str(position))
        position += 1

    for metric in plan.metrics:
        select_parts.append(f"{metric.expr_sql} as {metric.request_name}")
        position += 1

    if not select_parts:
        select_parts.append("*")

    anchor = registry.tables[plan.from_table]
    from_sql = f"{fully_qualified_table(anchor.physical_schema, anchor.physical_table)} {plan.from_alias}"

    join_sql_parts = []
    for join in plan.joins:
        if join.right_table == plan.from_table:
            joined_table_name = join.left_table
            left_alias = registry.tables[join.right_table].alias
            right_alias = registry.tables[join.left_table].alias
        else:
            joined_table_name = join.right_table
            left_alias = registry.tables[join.left_table].alias
            right_alias = registry.tables[join.right_table].alias

        joined_table = registry.tables[joined_table_name]
        join_expr = join.join_expr.replace("LEFT_TABLE.", f"{left_alias}.").replace(
            "RIGHT_TABLE.", f"{right_alias}."
        )
        join_sql_parts.append(
            f"{join.join_type.upper()} JOIN "
            f"{fully_qualified_table(joined_table.physical_schema, joined_table.physical_table)} "
            f"{joined_table.alias} ON {join_expr}"
        )

    sql = "select\n  " + ",\n  ".join(select_parts) + f"\nfrom {from_sql}"
    if join_sql_parts:
        sql += "\n" + "\n".join(join_sql_parts)
    if plan.where_clause:
        sql += f"\nwhere {plan.where_clause}"
    if plan.metrics and plan.dimensions:
        sql += f"\ngroup by {', '.join(group_by_positions)}"
    if not plan.derived_dimensions and not plan.derived_metrics:
        return sql + ";"

    outer_select_parts = []
    for output_name in plan.output_dimensions:
        derived = next((item for item in plan.derived_dimensions if item.alias == output_name), None)
        if derived is not None:
            outer_select_parts.append(f"{derived.expr_sql} as {derived.alias}")
        else:
            outer_select_parts.append(output_name)

    for output_name in plan.output_metrics:
        derived = next((item for item in plan.derived_metrics if item.alias == output_name), None)
        if derived is not None:
            outer_select_parts.append(f"{derived.expr_sql} as {derived.alias}")
        else:
            outer_select_parts.append(output_name)

    outer_sql = "select\n  " + ",\n  ".join(outer_select_parts) + "\nfrom (\n"
    outer_sql += "\n".join(f"  {line}" for line in sql.splitlines())
    outer_sql += "\n) semduck_base"
    return outer_sql + ";"
