from semduck.compiler.sql_compiler import compile_sql
from semduck.parser.request_parser import parse_request
from semduck.planner.resolver import build_query_plan
from semduck.registry.reader import load_semantic_view_registry


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


def test_compile_derived_metric_outer_select(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    plan = build_query_plan(
        parse_request("orders_semantic metrics total_revenue / 1000 as revenue_in_thousands"),
        registry,
    )
    sql = compile_sql(plan, registry)
    assert "from (\n  select" in sql
    assert "total_revenue / 1000 as revenue_in_thousands" in sql


def test_compile_derived_dimension_outer_select(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    plan = build_query_plan(
        parse_request(
            "orders_semantic dimensions region, case when region = 'US' then 'domestic' else 'intl' end as market_type metrics total_revenue"
        ),
        registry,
    )
    sql = compile_sql(plan, registry)
    assert "case when region = 'US' then 'domestic' else 'intl' end as market_type" in sql
