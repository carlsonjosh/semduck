from semduck import compile_request, execute_request


def test_compile_request(loaded_conn):
    compiled = compile_request(
        loaded_conn,
        "orders_semantic dimensions region metrics total_revenue where region = 'US'",
    )
    assert "sum(o.revenue) as total_revenue" in compiled.sql
    assert "where (o.region) = 'US'" in compiled.sql


def test_execute_request_single_table(loaded_conn):
    relation = execute_request(
        loaded_conn,
        "orders_semantic dimensions region metrics total_revenue where region = 'US'",
    )
    rows = relation.fetchall()
    assert rows == [("US", 250.0)]


def test_execute_request_direct_join(loaded_conn):
    relation = execute_request(
        loaded_conn,
        "orders_semantic dimensions customer_segment metrics total_revenue",
    )
    rows = relation.fetchall()
    assert len(rows) == 3


def test_execute_request_with_derived_metric(loaded_conn):
    relation = execute_request(
        loaded_conn,
        "orders_semantic metrics total_revenue / 1000 as revenue_in_thousands",
    )
    rows = relation.fetchall()
    assert rows == [(0.45,)]


def test_execute_request_with_derived_dimension(loaded_conn):
    relation = execute_request(
        loaded_conn,
        "orders_semantic dimensions region, case when region = 'US' then 'domestic' else 'intl' end as market_type metrics total_revenue",
    )
    rows = sorted(relation.fetchall())
    assert rows == [("CA", "intl", 200.0), ("US", "domestic", 250.0)]
