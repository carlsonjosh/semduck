from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import SemanticConcept, SemanticConceptField, SemanticConceptIndex


def normalize_phrase(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def field_name_phrases(name: str) -> set[str]:
    humanized = normalize_phrase(name)
    phrases = {name.lower(), humanized}
    tokens = humanized.split()
    if tokens:
        last = tokens[-1]
        if last.endswith("y"):
            phrases.add(" ".join([*tokens[:-1], f"{last[:-1]}ies"]))
        else:
            phrases.add(" ".join([*tokens[:-1], f"{last}s"]))
    return {phrase for phrase in phrases if phrase}


def compute_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def concept_lookup(index: SemanticConceptIndex) -> dict[tuple[str, str], SemanticConcept]:
    return {(concept.concept_id, concept.concept_kind): concept for concept in index.concepts}


def view_field_lookup(index: SemanticConceptIndex) -> dict[str, dict[str, list[SemanticConceptField]]]:
    lookup: dict[str, dict[str, list[SemanticConceptField]]] = {}
    for field in index.fields:
        per_view = lookup.setdefault(field.view_name, {})
        per_view.setdefault(field.field_name, []).append(field)
    return lookup
