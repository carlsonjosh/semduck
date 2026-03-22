from duckdb_semantic.compiler.sql_compiler import compile_sql
from duckdb_semantic.parser.request_parser import parse_request
from duckdb_semantic.planner.resolver import build_query_plan
from duckdb_semantic.registry.reader import load_semantic_view_registry


def test_compile_dimensions_and_metrics(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    plan = build_query_plan(
        parse_request("orders_semantic dimensions region metrics total_revenue"),
        registry,
    )
    sql = compile_sql(plan, registry)
    assert "sum(o.revenue) as total_revenue" in sql
    assert "group by 1" in sql


def test_compile_select_star(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    plan = build_query_plan(parse_request("orders_semantic"), registry)
    sql = compile_sql(plan, registry)
    assert "select\n  *" in sql


def test_compile_join_sql(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    plan = build_query_plan(
        parse_request("orders_semantic dimensions customer_segment metrics total_revenue"),
        registry,
    )
    sql = compile_sql(plan, registry)
    assert "LEFT JOIN mart.orders_base o" not in sql
    assert "LEFT JOIN mart.customers_base c" in sql

