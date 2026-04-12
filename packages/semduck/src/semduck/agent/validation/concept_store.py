from __future__ import annotations

import json

from .concept_builder import build_semantic_concepts
from .models import SemanticConcept, SemanticConceptField, SemanticConceptIndex
from .policy import ValidationPolicy


def load_semantic_concepts(conn, fingerprint: str) -> SemanticConceptIndex | None:
    concept_rows = conn.execute(
        """
        select concept_id, concept_kind, metadata_json
        from semantic.semantic_concepts
        where fingerprint = ?
        order by concept_kind, concept_id
        """,
        [fingerprint],
    ).fetchall()
    if not concept_rows:
        return None
    phrase_rows = conn.execute(
        """
        select concept_id, concept_kind, phrase
        from semantic.semantic_concept_phrases
        where fingerprint = ?
        order by concept_kind, concept_id, phrase
        """,
        [fingerprint],
    ).fetchall()
    field_rows = conn.execute(
        """
        select concept_id, concept_kind, view_name, table_name, field_name, field_kind, is_preferred
        from semantic.semantic_concept_fields
        where fingerprint = ?
        order by view_name, concept_kind, concept_id, field_name
        """,
        [fingerprint],
    ).fetchall()
    phrase_lookup: dict[tuple[str, str], list[str]] = {}
    for concept_id, concept_kind, phrase in phrase_rows:
        phrase_lookup.setdefault((concept_id, concept_kind), []).append(phrase)
    concepts = [
        SemanticConcept(
            concept_id=concept_id,
            concept_kind=concept_kind,
            phrases=phrase_lookup.get((concept_id, concept_kind), []),
            metadata=json.loads(metadata_json) if metadata_json else {},
        )
        for concept_id, concept_kind, metadata_json in concept_rows
    ]
    fields = [
        SemanticConceptField(
            concept_id=concept_id,
            concept_kind=concept_kind,
            view_name=view_name,
            table_name=table_name,
            field_name=field_name,
            field_kind=field_kind,
            is_preferred=bool(is_preferred),
        )
        for concept_id, concept_kind, view_name, table_name, field_name, field_kind, is_preferred in field_rows
    ]
    return SemanticConceptIndex(fingerprint=fingerprint, concepts=concepts, fields=fields)


def persist_semantic_concepts(conn, index: SemanticConceptIndex, policy: ValidationPolicy) -> None:
    conn.execute(
        """
        insert into semantic.semantic_concept_sets (fingerprint, policy_version, status)
        values (?, ?, 'ready')
        on conflict do nothing
        """,
        [index.fingerprint, policy.policy_version],
    )
    for concept in index.concepts:
        conn.execute(
            """
            insert into semantic.semantic_concepts (fingerprint, concept_id, concept_kind, metadata_json)
            values (?, ?, ?, ?)
            on conflict do nothing
            """,
            [
                index.fingerprint,
                concept.concept_id,
                concept.concept_kind,
                json.dumps(concept.metadata, sort_keys=True),
            ],
        )
        for phrase in concept.phrases:
            conn.execute(
                """
                insert into semantic.semantic_concept_phrases (fingerprint, concept_id, concept_kind, phrase)
                values (?, ?, ?, ?)
                on conflict do nothing
                """,
                [index.fingerprint, concept.concept_id, concept.concept_kind, phrase],
            )
    for field in index.fields:
        conn.execute(
            """
            insert into semantic.semantic_concept_fields (
                fingerprint, concept_id, concept_kind, view_name, table_name, field_name, field_kind, is_preferred
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict do nothing
            """,
            [
                index.fingerprint,
                field.concept_id,
                field.concept_kind,
                field.view_name,
                field.table_name,
                field.field_name,
                field.field_kind,
                field.is_preferred,
            ],
        )


def ensure_semantic_concepts(conn, policy: ValidationPolicy) -> SemanticConceptIndex:
    built = build_semantic_concepts(conn, policy)
    cached = load_semantic_concepts(conn, built.fingerprint)
    if cached is not None:
        return cached
    persist_semantic_concepts(conn, built, policy)
    return built
