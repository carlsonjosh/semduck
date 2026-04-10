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
    assert "sum(order_revenue) as total_revenue" in sql
    assert "o.revenue as order_revenue" in sql
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


def test_compile_metric_fact_and_metric_references(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    plan = build_query_plan(
        parse_request("orders_semantic metrics margin_pct"),
        registry,
    )
    sql = compile_sql(plan, registry)
    assert "o.revenue - o.unit_costs as order_profit" in sql
    assert "order_profit as row_profit_metric__input" in sql
    assert "o.revenue as order_revenue" in sql
    assert "sum(row_profit_metric__input) as total_profit" in sql
    assert "sum(order_revenue) as total_revenue" in sql
    assert "(total_profit) / (total_revenue) as margin_pct" in sql


def test_compile_row_level_helper_derived_metric(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    plan = build_query_plan(
        parse_request("orders_semantic metrics row_profit_metric / order_revenue as row_margin_pct"),
        registry,
    )
    sql = compile_sql(plan, registry)
    assert "order_profit as row_profit_metric__input" in sql
    assert "o.revenue as order_revenue" in sql
    assert "row_profit_metric__input / order_revenue as row_margin_pct" in sql


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


def test_compile_derived_time_dimension_groups_by_derived_bucket(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    plan = build_query_plan(
        parse_request(
            "orders_semantic dimensions date_trunc('month', order_date) as order_month metrics total_revenue"
        ),
        registry,
    )
    sql = compile_sql(plan, registry)
    assert "select\n  order_month,\n  total_revenue" in sql
    assert "date_trunc('month', order_date) as order_month" in sql
    assert "order_date,\n      o.revenue as order_revenue" in sql
    assert "group by 1" in sql
    assert "date_trunc('month', order_date) as order_month,\n    sum(order_revenue) as total_revenue" in sql


def test_compile_derived_dimension_groups_by_derived_value_not_dependency(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    plan = build_query_plan(
        parse_request(
            "orders_semantic dimensions case when region = 'US' then 'domestic' else 'intl' end as market_type metrics total_revenue"
        ),
        registry,
    )
    sql = compile_sql(plan, registry)
    assert "case when region = 'US' then 'domestic' else 'intl' end as market_type,\n    sum(order_revenue) as total_revenue" in sql
    assert "select\n  market_type,\n  total_revenue" in sql
    assert "group by 1" in sql


def test_compile_order_by_and_limit_on_outer_query(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    plan = build_query_plan(
        parse_request("orders_semantic dimensions region metrics total_revenue order_by total_revenue desc limit 2"),
        registry,
    )
    sql = compile_sql(plan, registry)
    assert "order by total_revenue desc" in sql.lower()
    assert "limit 2" in sql.lower()
    assert "group by 1\norder by" not in sql.lower()
