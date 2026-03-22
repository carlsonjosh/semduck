from semduck import get_semantic_view, load_semantic_yaml


VALID_YAML = """
name: sample
tables:
  - name: orders
    base_table:
      schema: mart
      table: orders_base
    primary_key:
      columns: [order_id]
    dimensions:
      - name: region
        expr: region
    metrics:
      - name: order_count
        metric_type: count
        expr: order_id
"""


def test_registry_loads_and_reads(conn):
    result = load_semantic_yaml(conn, VALID_YAML)
    assert result.validated_only is False

    registry = get_semantic_view(conn, "sample")
    assert registry.view_name == "sample"
    assert "orders" in registry.tables
    assert "region" in registry.tables["orders"].dimensions
    assert "order_count" in registry.tables["orders"].metrics


def test_replace_existing(conn):
    load_semantic_yaml(conn, VALID_YAML)
    replacement = """
name: sample
tables:
  - name: orders
    base_table:
      table: orders_base
    dimensions:
      - name: country
        expr: country
"""
    load_semantic_yaml(conn, replacement)
    registry = get_semantic_view(conn, "sample")
    assert "country" in registry.tables["orders"].dimensions
    assert "region" not in registry.tables["orders"].dimensions
