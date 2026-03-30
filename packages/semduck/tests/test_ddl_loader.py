from semduck import compile_request_sql, load_semantic_ddl


VALID_DDL = """
create semantic view orders_semantic as
table orders as mart.orders_base
  dimensions (
    region as region type varchar
  )
  metrics (
    sum(revenue) as total_revenue,
    count(order_id) as order_count
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
    sum(revenue) as total_revenue
  );
"""
    result = load_semantic_ddl(loaded_conn, ddl)
    assert result.view_name == "replacement_semantic"
    stored = loaded_conn.sql(
        "select view_name from semantic.semantic_views where view_name = 'replacement_semantic'"
    ).fetchone()
    assert stored == ("replacement_semantic",)


def test_load_semantic_ddl_supports_formula_metrics(conn):
    conn.execute("create schema mart")
    conn.execute(
        """
        create table mart.orders_base (
            order_id integer,
            order_total double
        )
        """
    )
    ddl = """
create semantic view orders_semantic as
table orders as mart.orders_base
  facts (
    order_total as order_total
  )
  metrics (
    sum(order_total) as total_revenue,
    count(order_id) as order_count,
    total_revenue / order_count as average_order_value
  );
"""
    load_semantic_ddl(conn, ddl)
    sql = compile_request_sql(conn, "orders_semantic metrics average_order_value")
    assert "sum(order_total) as total_revenue" in sql
    assert "count(order_count__input) as order_count" in sql
    assert "(total_revenue) / (order_count) as average_order_value" in sql


def test_load_semantic_ddl_rejects_alias_first_syntax(conn):
    ddl = """
create semantic view orders_semantic as
table orders as mart.orders_base
  metrics (
    total_revenue as sum(revenue)
  );
"""
    try:
        load_semantic_ddl(conn, ddl, validate_only=True)
    except Exception as exc:
        assert "Invalid metric definition" in str(exc)
    else:
        raise AssertionError("expected alias-first DDL to fail")
