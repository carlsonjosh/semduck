from duckdb_semantic import load_semantic_yaml
from duckdb_semantic.errors import SemanticValidationError


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

