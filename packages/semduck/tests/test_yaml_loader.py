from semduck import compile_request_sql, load_semantic_yaml
from semduck.errors import SemanticValidationError


VALID_YAML = """
name: sample
tables:
  - name: orders
    base_table:
      table: orders_base
    dimensions:
      - name: region
        expr: region
    metrics:
      - name: order_count
        metric_type: count
        expr: order_id
"""


def test_valid_yaml_validate_only(conn):
    result = load_semantic_yaml(conn, VALID_YAML, validate_only=True)
    assert result.ok is True
    assert result.validated_only is True


def test_duplicate_table_rejected(conn):
    yaml_text = """
name: sample
tables:
  - name: orders
    base_table:
      table: orders_base
  - name: orders
    base_table:
      table: orders_other
"""
    try:
        load_semantic_yaml(conn, yaml_text, validate_only=True)
    except SemanticValidationError:
        pass
    else:
        raise AssertionError("expected SemanticValidationError")


def test_missing_expr_rejected(conn):
    yaml_text = """
name: sample
tables:
  - name: orders
    base_table:
      table: orders_base
    dimensions:
      - name: region
"""
    try:
        load_semantic_yaml(conn, yaml_text, validate_only=True)
    except SemanticValidationError:
        pass
    else:
        raise AssertionError("expected SemanticValidationError")


def test_join_to_missing_table_rejected(conn):
    yaml_text = """
name: sample
tables:
  - name: orders
    base_table:
      table: orders_base
joins:
  - name: bad_join
    left_table: orders
    right_table: customers
    join_type: left
    join_expr: LEFT_TABLE.customer_id = RIGHT_TABLE.customer_id
"""
    try:
        load_semantic_yaml(conn, yaml_text, validate_only=True)
    except SemanticValidationError:
        pass
    else:
        raise AssertionError("expected SemanticValidationError")


def test_yaml_formula_metrics_compile(conn):
    conn.execute("create schema mart")
    conn.execute(
        """
        create table mart.orders_base (
            order_id integer,
            revenue double,
            unit_costs double
        )
        """
    )
    yaml_text = """
name: orders_semantic
tables:
  - name: orders
    base_table:
      schema: mart
      table: orders_base
    facts:
      - name: order_revenue
        expr: revenue
      - name: order_profit
        expr: revenue - unit_costs
    metrics:
      - name: total_revenue
        metric_type: sum
        expr: order_revenue
      - name: total_profit
        metric_type: sum
        expr: order_profit
      - name: margin_pct
        metric_type: expr
        expr: total_profit / total_revenue
"""
    load_semantic_yaml(conn, yaml_text)
    sql = compile_request_sql(conn, "orders_semantic metrics margin_pct")
    assert "sum(order_revenue) as total_revenue" in sql
    assert "sum(order_profit) as total_profit" in sql
    assert "(total_profit) / (total_revenue) as margin_pct" in sql
