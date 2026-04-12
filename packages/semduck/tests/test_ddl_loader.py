from semduck import compile_request_sql, load_semantic_ddl
from semduck.authoring.ddl_loader import parse_semantic_ddl


VALID_DDL = """
create semantic view orders_semantic as
table mart.orders_base as orders
  dimensions (
    region as region type varchar
  )
  metrics (
    sum(revenue) as total_revenue,
    count(order_id) as order_count
  )

table mart.customers_base as customers
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
table mart.orders_base as orders
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
table mart.orders_base as orders
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
    assert "count(order_count__order_id) as order_count" in sql
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
        assert "Unexpected semantic DDL line" in str(exc)
    else:
        raise AssertionError("expected semantic-name-first table declaration to fail")


def test_load_semantic_ddl_accepts_ai_context(conn):
    ddl = """
create semantic view orders_semantic as
ai_context '{"concepts":[{"concept_id":"recent","concept_kind":"modifier","phrases":["recent"]}]}'
table mart.orders_base as orders
  ai_context '{"phrases":["orders"]}'
  dimensions (
    region as region ai_context '{"concept_id":"region","phrases":["region","regions"]}'
  )
  metrics (
    count(order_id) as order_count ai_context '{"concept_id":"order_count","phrases":["order count"]}'
  );
"""
    result = load_semantic_ddl(conn, ddl, validate_only=True)
    assert result.ok is True


def test_parse_semantic_ddl_accepts_native_ai_context_blocks():
    ddl = """
create semantic view orders_semantic as
ai_context (
  concept recent (
    concept_kind modifier
    phrases ('recent', 'recently')
    default_window '30 days'
    time_dimension order_date
  )
)
table mart.orders_base as orders
  ai_context (
    phrases ('orders')
  )
  dimensions (
    region as region ai_context (
      concept region (
        phrases ('region', 'regions')
        preferred true
      )
      concept geography_region (
        phrases ('sales region')
        notes 'Regional business label'
      )
    )
  )
  metrics (
    count(order_id) as order_count ai_context (
      concept order_count (
        phrases ('order count')
        requires_filter false
      )
    )
  )

join orders_to_customers:
  left_table orders
  right_table customers
  join_type left
  on LEFT_TABLE.customer_id = RIGHT_TABLE.customer_id
  ai_context (
    notes 'Orders join to customer grain'
  );
"""
    spec = parse_semantic_ddl(ddl)
    assert spec["ai_context"]["concepts"][0] == {
        "concept_id": "recent",
        "concept_kind": "modifier",
        "phrases": ["recent", "recently"],
        "default_window": "30 days",
        "time_dimension": "order_date",
    }
    assert spec["tables"][0]["ai_context"] == {"phrases": ["orders"]}
    assert spec["tables"][0]["dimensions"][0]["ai_context"]["concepts"] == [
        {
            "concept_id": "region",
            "phrases": ["region", "regions"],
            "preferred": True,
        },
        {
            "concept_id": "geography_region",
            "phrases": ["sales region"],
            "notes": "Regional business label",
        },
    ]
    assert spec["tables"][0]["metrics"][0]["ai_context"]["concepts"] == [
        {
            "concept_id": "order_count",
            "phrases": ["order count"],
            "requires_filter": False,
        }
    ]
    assert spec["joins"][0]["ai_context"] == {"notes": "Orders join to customer grain"}


def test_load_semantic_ddl_rejects_unknown_native_ai_context_property(conn):
    ddl = """
create semantic view orders_semantic as
table mart.orders_base as orders
  dimensions (
    region as region ai_context (
      concept region (
        unsupported_key foo
      )
    )
  );
"""
    try:
        load_semantic_ddl(conn, ddl, validate_only=True)
    except Exception as exc:
        assert "Unknown concept region property: unsupported_key" in str(exc)
    else:
        raise AssertionError("expected native ai_context validation failure")
