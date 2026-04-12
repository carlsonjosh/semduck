from __future__ import annotations

from semduck import load_semantic_ddl
from semduck.agent.validation.concept_store import ensure_semantic_concepts, load_semantic_concepts
from semduck.agent.validation.policy import DEFAULT_VALIDATION_POLICY


def test_ensure_semantic_concepts_persists_and_reloads(ecommerce_registry_conn):
    index = ensure_semantic_concepts(ecommerce_registry_conn, DEFAULT_VALIDATION_POLICY)
    loaded = load_semantic_concepts(ecommerce_registry_conn, index.fingerprint)

    assert loaded is not None
    assert loaded.fingerprint == index.fingerprint
    assert any(concept.concept_id == "customer_state" for concept in loaded.concepts)
    assert any(
        field.concept_id == "customer_state"
        and field.view_name == "orders_semantic"
        and field.field_name == "customer_state"
        for field in loaded.fields
    )
    assert any(
        field.concept_id == "customer_state"
        and field.view_name == "customer_semantic"
        and field.field_name == "state"
        for field in loaded.fields
    )


def test_ensure_semantic_concepts_reuses_fingerprint(ecommerce_registry_conn):
    first = ensure_semantic_concepts(ecommerce_registry_conn, DEFAULT_VALIDATION_POLICY)
    second = ensure_semantic_concepts(ecommerce_registry_conn, DEFAULT_VALIDATION_POLICY)

    count = ecommerce_registry_conn.execute(
        "select count(*) from semantic.semantic_concept_sets where fingerprint = ?",
        [first.fingerprint],
    ).fetchone()[0]

    assert second.fingerprint == first.fingerprint
    assert count == 1


def test_load_semantic_ddl_eagerly_populates_concept_tables(conn):
    ddl = """
create semantic view sample as
ai_context (
  concept recent (
    concept_kind modifier
    phrases ('recent')
    default_window '30 days'
    time_dimension order_date
  )
)
table mart.orders_base as orders
  dimensions (
    order_date as order_date type date ai_context (
      concept order_date (
        phrases ('order date')
      )
    )
  )
  metrics (
    count(order_id) as order_count
  );
"""
    load_semantic_ddl(conn, ddl)

    concept_sets = conn.execute("select count(*) from semantic.semantic_concept_sets").fetchone()[0]
    concepts = conn.execute("select count(*) from semantic.semantic_concepts").fetchone()[0]
    concept_fields = conn.execute("select count(*) from semantic.semantic_concept_fields").fetchone()[0]
    concept_phrases = conn.execute("select count(*) from semantic.semantic_concept_phrases").fetchone()[0]

    assert concept_sets == 1
    assert concepts > 0
    assert concept_fields > 0
    assert concept_phrases > 0


def test_object_level_multiple_concepts_bind_to_same_metric(conn):
    ddl = """
create semantic view sample as
table mart.orders_base as orders
  metrics (
    count(order_id) as average_order_value ai_context (
      concept average_order_value (
        phrases ('average order value', 'AOV')
      )
      concept ticket_size (
        phrases ('ticket size')
      )
    )
  );
"""
    load_semantic_ddl(conn, ddl)

    concept_ids = conn.execute(
        """
        select concept_id
        from semantic.semantic_concepts
        where concept_kind = 'metric'
        order by concept_id
        """
    ).fetchall()
    ticket_fields = conn.execute(
        """
        select field_name
        from semantic.semantic_concept_fields
        where concept_id = 'ticket_size' and concept_kind = 'metric'
        """
    ).fetchall()
    ticket_phrases = conn.execute(
        """
        select phrase
        from semantic.semantic_concept_phrases
        where concept_id = 'ticket_size' and concept_kind = 'metric'
        order by phrase
        """
    ).fetchall()

    assert ("ticket_size",) in concept_ids
    assert ticket_fields == [("average_order_value",)]
    assert ticket_phrases == [("ticket size",)]
