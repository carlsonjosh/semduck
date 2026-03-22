from semduck.errors import SemanticJoinError, SemanticResolutionError
from semduck.parser.request_parser import parse_request
from semduck.planner.resolver import build_query_plan
from semduck.registry.reader import load_semantic_view_registry


def test_single_table_resolution(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    plan = build_query_plan(
        parse_request("orders_semantic dimensions region metrics total_revenue"),
        registry,
    )
    assert plan.from_table == "orders"
    assert len(plan.dimensions) == 1
    assert len(plan.metrics) == 1


def test_unknown_dimension_rejected(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    try:
        build_query_plan(parse_request("orders_semantic dimensions missing_dim"), registry)
    except SemanticResolutionError:
        pass
    else:
        raise AssertionError("expected SemanticResolutionError")


def test_direct_join_resolution(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    plan = build_query_plan(
        parse_request("orders_semantic dimensions customer_segment metrics total_revenue"),
        registry,
    )
    assert len(plan.joins) == 1


def test_missing_direct_join_rejected(conn):
    conn.execute("insert into semantic.semantic_views (view_name) values ('sample')")
    conn.execute(
        """
        insert into semantic.semantic_view_tables
        (view_name, table_name, physical_table, table_alias)
        values
        ('sample', 'a', 'a_tbl', 'a'),
        ('sample', 'b', 'b_tbl', 'b')
        """
    )
    conn.execute(
        """
        insert into semantic.metrics
        (view_name, table_name, metric_name, metric_type, expr)
        values ('sample', 'a', 'm1', 'sum', 'col1')
        """
    )
    conn.execute(
        """
        insert into semantic.dimensions
        (view_name, table_name, dimension_name, dimension_kind, expr)
        values ('sample', 'b', 'd1', 'dimension', 'col2')
        """
    )
    registry = load_semantic_view_registry(conn, "sample")
    try:
        build_query_plan(parse_request("sample dimensions d1 metrics m1"), registry)
    except SemanticJoinError:
        pass
    else:
        raise AssertionError("expected SemanticJoinError")
