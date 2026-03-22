from semduck import load_semantic_ddl


VALID_DDL = """
create semantic view orders_semantic as
table orders as mart.orders_base
  dimensions (
    region as region type varchar
  )
  metrics (
    total_revenue as sum(revenue),
    order_count as count(order_id)
  )

table customers as mart.customers_base
  dimensions (
    customer_segment as customer_segment
  )

join orders_to_customers:
  left_table orders
  right_table customers
  join_type left
  on LEFT_TABLE.customer_id = RIGHT_TABLE.customer_id;
"""


def test_load_semantic_ddl_validate_only(conn):
    result = load_semantic_ddl(conn, VALID_DDL, validate_only=True)
    assert result.ok is True
    assert result.validated_only is True


def test_load_semantic_ddl_persists_registry(loaded_conn):
    ddl = """
create semantic view replacement_semantic as
table orders as mart.orders_base
  dimensions (
    region as region
  )
  metrics (
    total_revenue as sum(revenue)
  );
"""
    result = load_semantic_ddl(loaded_conn, ddl)
    assert result.view_name == "replacement_semantic"
    stored = loaded_conn.sql(
        "select view_name from semantic.semantic_views where view_name = 'replacement_semantic'"
    ).fetchone()
    assert stored == ("replacement_semantic",)
