from __future__ import annotations

from .concept_store import ensure_semantic_concepts
from .intent_builder import resolve_question_intent
from .policy import DEFAULT_VALIDATION_POLICY, ValidationPolicy


def infer_intent(question: str, conn, *, policy: ValidationPolicy = DEFAULT_VALIDATION_POLICY):
    concept_index = ensure_semantic_concepts(conn, policy)
    return resolve_question_intent(question, concept_index, policy=policy)
