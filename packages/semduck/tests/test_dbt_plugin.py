import json

from semduck import compile_request_sql, load_semantic_ddl, load_semantic_spec, register_connection


VALID_SPEC = {
    "name": "sample",
    "tables": [
        {
            "name": "orders",
            "base_table": {"table": "orders_base"},
            "dimensions": [{"name": "region", "expr": "region"}],
            "metrics": [{"name": "order_count", "metric_type": "count", "expr": "order_id"}],
        }
    ],
}


def test_load_semantic_spec_validate_only(conn):
    result = load_semantic_spec(conn, VALID_SPEC, validate_only=True)
    assert result.ok is True
    assert result.validated_only is True


def test_register_connection_registers_udfs(conn):
    register_connection(conn)
    spec_json = json.dumps(VALID_SPEC).replace("'", "''")

    check_result = conn.sql(
        f"select semduck_check_resolved_spec('{spec_json}') as status"
    ).fetchone()[0]
    assert check_result == "ok check view_name=sample"


def test_compile_request_sql_returns_sql(loaded_conn):
    sql = compile_request_sql(
        loaded_conn, "orders_semantic dimensions region metrics total_revenue"
    )
    assert "select" in sql.lower()
    assert "mart.orders_base" in sql


def test_register_connection_registers_ddl_udfs(conn):
    register_connection(conn)
    ddl_text = """
create semantic view sample as
table orders as mart.orders_base
  dimensions (
    region as region
  )
  metrics (
    order_count as count(order_id)
  );
"""
    ddl_sql = ddl_text.replace("'", "''")
    status = conn.sql(
        f"select semduck_check_ddl('{ddl_sql}') as status"
    ).fetchone()[0]
    assert status == "ok check view_name=sample"
