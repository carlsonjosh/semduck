from semduck import get_semantic_view, load_semantic_yaml


VALID_YAML = """
name: sample
ai_context:
  concepts:
    - concept_id: region
      concept_kind: dimension
      phrases: [region, regions]
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
        ai_context:
          concept_id: region
          phrases: [region, regions]
    metrics:
      - name: order_count
        expr: count(order_id)
        ai_context:
          concept_id: order_count
          phrases: [order count]
"""


def test_registry_loads_and_reads(conn):
    result = load_semantic_yaml(conn, VALID_YAML)
    assert result.validated_only is False

    registry = get_semantic_view(conn, "sample")
    assert registry.view_name == "sample"
    assert registry.ai_context is not None
    assert "orders" in registry.tables
    assert "region" in registry.tables["orders"].dimensions
    assert "order_count" in registry.tables["orders"].metrics
    assert registry.tables["orders"].dimensions["region"].ai_context == {
        "concept_id": "region",
        "phrases": ["region", "regions"],
    }


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
