from semduck.errors import SemanticResolutionError
from semduck.planner.where_rewriter import rewrite_where_clause
from semduck.registry.reader import load_semantic_view_registry


def test_rewrite_dimension_reference(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    rewritten = rewrite_where_clause("region = 'US'", registry)
    assert rewritten == "(o.region) = 'US'"


def test_rewrite_fact_reference(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    rewritten = rewrite_where_clause("revenue > 100", registry)
    assert rewritten == "(o.revenue) > 100"


def test_metric_in_where_rejected(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    try:
        rewrite_where_clause("total_revenue > 100", registry)
    except SemanticResolutionError:
        pass
    else:
        raise AssertionError("expected SemanticResolutionError")
