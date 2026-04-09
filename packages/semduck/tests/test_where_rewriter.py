from semduck.errors import SemanticResolutionError
from semduck.planner.where_rewriter import rewrite_where_clause
from semduck.registry.reader import load_semantic_view_registry


def test_rewrite_dimension_reference(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    rewritten = rewrite_where_clause("region = 'US'", registry)
    assert rewritten == "(o.region) = 'US'"


def test_rewrite_fact_reference(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    rewritten = rewrite_where_clause("order_revenue > 100", registry)
    assert rewritten == "(o.revenue) > 100"


def test_rewrite_leaves_qualified_identifier_unchanged(conn):
    conn.execute("create schema mart")
    conn.execute("create table mart.products_base (product_id varchar, is_active boolean)")
    conn.execute(
        """
        insert into semantic.semantic_views (view_name) values ('products_semantic')
        """
    )
    conn.execute(
        """
        insert into semantic.semantic_view_tables
        (view_name, table_name, physical_schema, physical_table, table_alias, primary_key_columns)
        values ('products_semantic', 'products', 'mart', 'products_base', 'p', '["product_id"]')
        """
    )
    conn.execute(
        """
        insert into semantic.dimensions
        (view_name, table_name, dimension_name, dimension_kind, expr, data_type)
        values ('products_semantic', 'products', 'is_active', 'dimension', 'is_active', 'boolean')
        """
    )
    registry = load_semantic_view_registry(conn, "products_semantic")
    rewritten = rewrite_where_clause("p.is_active = FALSE", registry)
    assert rewritten == "p.is_active = FALSE"


def test_metric_in_where_rejected(loaded_conn):
    registry = load_semantic_view_registry(loaded_conn, "orders_semantic")
    try:
        rewrite_where_clause("total_revenue > 100", registry)
    except SemanticResolutionError:
        pass
    else:
        raise AssertionError("expected SemanticResolutionError")
