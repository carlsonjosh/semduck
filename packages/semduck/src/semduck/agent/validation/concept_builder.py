from __future__ import annotations

from typing import Any

from semduck.api import get_semantic_view, list_semantic_views

from .concepts import compute_fingerprint, field_name_phrases, normalize_phrase
from .models import SemanticConcept, SemanticConceptField, SemanticConceptIndex
from .policy import ValidationPolicy


def _merge_ai_context(*contexts: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    phrases: list[str] = []
    concepts: list[dict[str, Any]] = []
    concept_id_sources: list[str] = []

    for context in contexts:
        if not context:
            continue
        if "phrases" in context:
            phrases.extend(str(item) for item in context.get("phrases", []) if str(item).strip())
        if "concepts" in context:
            concepts.extend(item for item in context.get("concepts", []) if isinstance(item, dict))
        if "concept_id" in context and context["concept_id"]:
            concept_id_sources.append(str(context["concept_id"]).strip())
        for key, value in context.items():
            if key in {"phrases", "concepts"}:
                continue
            merged[key] = value

    if concept_id_sources:
        explicit_ids = {value for value in concept_id_sources if value}
        if len(explicit_ids) > 1:
            raise ValueError(f"Conflicting ai_context concept_id values: {sorted(explicit_ids)}")
        merged["concept_id"] = concept_id_sources[-1]
    if phrases:
        merged["phrases"] = sorted({normalize_phrase(item) for item in phrases if normalize_phrase(item)})
    if concepts:
        merged["concepts"] = concepts
    return merged


def _kind_for_object(object_type: str) -> str:
    if object_type == "metric":
        return "metric"
    return "dimension"


def _add_concept(
    concepts: dict[tuple[str, str], SemanticConcept],
    *,
    concept_id: str,
    concept_kind: str,
    phrases: set[str],
    metadata: dict[str, Any] | None = None,
) -> None:
    key = (concept_id, concept_kind)
    existing = concepts.get(key)
    if existing is None:
        concepts[key] = SemanticConcept(
            concept_id=concept_id,
            concept_kind=concept_kind,
            phrases=sorted(phrases),
            metadata=metadata or {},
        )
        return
    concepts[key] = SemanticConcept(
        concept_id=existing.concept_id,
        concept_kind=existing.concept_kind,
        phrases=sorted(set(existing.phrases).union(phrases)),
        metadata={**existing.metadata, **(metadata or {})},
    )


def _register_field_concept(
    concepts: dict[tuple[str, str], SemanticConcept],
    fields: list[SemanticConceptField],
    *,
    view_name: str,
    table_name: str,
    field_name: str,
    field_kind: str,
    object_context: dict[str, Any],
) -> None:
    concept_kind = _kind_for_object(field_kind)
    declared_concepts = [
        concept for concept in object_context.get("concepts", []) if isinstance(concept, dict)
    ]
    if not declared_concepts:
        declared_concepts = [object_context]

    for declared_concept in declared_concepts:
        concept_id = str(
            declared_concept.get("concept_id")
            or object_context.get("concept_id")
            or field_name
        ).strip()
        metadata = {}
        if "default_window" in declared_concept:
            metadata["default_window"] = declared_concept["default_window"]
        elif "default_window" in object_context:
            metadata["default_window"] = object_context["default_window"]
        if object_context.get("concepts"):
            phrases = set(declared_concept.get("phrases", []))
            if not phrases:
                phrases = set(field_name_phrases(field_name))
        else:
            phrases = set(field_name_phrases(field_name))
            phrases.update(object_context.get("phrases", []))
            phrases.update(declared_concept.get("phrases", []))
        _add_concept(
            concepts,
            concept_id=concept_id,
            concept_kind=concept_kind,
            phrases={normalize_phrase(item) for item in phrases if normalize_phrase(item)},
            metadata=metadata,
        )
        fields.append(
            SemanticConceptField(
                concept_id=concept_id,
                concept_kind=concept_kind,
                view_name=view_name,
                table_name=table_name,
                field_name=field_name,
                field_kind=field_kind,
                is_preferred=bool(
                    declared_concept.get("preferred", object_context.get("preferred", False))
                ),
            )
        )


def _register_scope_concepts(
    concepts: dict[tuple[str, str], SemanticConcept],
    fields: list[SemanticConceptField],
    *,
    view_name: str,
    time_dimensions: list[tuple[str, str]],
    scope_context: dict[str, Any] | None,
) -> None:
    if not scope_context:
        return
    for concept in scope_context.get("concepts", []):
        concept_id = str(concept["concept_id"]).strip()
        concept_kind = str(concept.get("concept_kind") or "modifier").strip()
        phrases = {normalize_phrase(item) for item in concept.get("phrases", []) if normalize_phrase(str(item))}
        metadata = {
            key: value
            for key, value in concept.items()
            if key not in {"concept_id", "concept_kind", "phrases"}
        }
        _add_concept(
            concepts,
            concept_id=concept_id,
            concept_kind=concept_kind,
            phrases=phrases,
            metadata=metadata,
        )
        target_dimension = concept.get("time_dimension")
        if concept_kind not in {"modifier", "time_modifier"} and target_dimension is None:
            continue
        for table_name, field_name in time_dimensions:
            if target_dimension is not None and field_name != target_dimension:
                continue
            fields.append(
                SemanticConceptField(
                    concept_id=concept_id,
                    concept_kind=concept_kind,
                    view_name=view_name,
                    table_name=table_name,
                    field_name=field_name,
                    field_kind="time_dimension",
                    is_preferred=field_name == target_dimension or target_dimension is None,
                )
            )


def build_semantic_concepts(conn, policy: ValidationPolicy) -> SemanticConceptIndex:
    concepts: dict[tuple[str, str], SemanticConcept] = {}
    fields: list[SemanticConceptField] = []
    fingerprint_payload: dict[str, Any] = {"views": {}, "policy_version": policy.policy_version}

    for concept in policy.generic_modifier_concepts:
        _add_concept(
            concepts,
            concept_id=str(concept["concept_id"]),
            concept_kind=str(concept["concept_kind"]),
            phrases={normalize_phrase(item) for item in concept.get("phrases", ()) if normalize_phrase(str(item))},
            metadata={
                key: value
                for key, value in concept.items()
                if key not in {"concept_id", "concept_kind", "phrases"}
            },
        )

    for view_name in list_semantic_views(conn):
        registry = get_semantic_view(conn, view_name)
        view_payload: dict[str, Any] = {
            "ai_context": registry.ai_context or {},
            "tables": {},
            "joins": [
                {
                    "left_table": join.left_table,
                    "right_table": join.right_table,
                    "join_type": join.join_type,
                    "join_expr": join.join_expr,
                    "ai_context": join.ai_context or {},
                }
                for join in registry.joins
            ],
        }
        time_dimensions: list[tuple[str, str]] = []
        for table_name, table in sorted(registry.tables.items()):
            table_payload: dict[str, Any] = {
                "ai_context": table.ai_context or {},
                "dimensions": {},
                "metrics": {},
                "facts": {},
            }
            for field_name, obj in sorted(table.dimensions.items()):
                field_payload = {
                    "object_type": obj.object_type,
                    "expr": obj.expr,
                    "ai_context": obj.ai_context or {},
                }
                table_payload["dimensions"][field_name] = field_payload
                if obj.object_type == "time_dimension":
                    time_dimensions.append((table_name, field_name))
                object_context = obj.ai_context or {}
                _register_field_concept(
                    concepts,
                    fields,
                    view_name=view_name,
                    table_name=table_name,
                    field_name=field_name,
                    field_kind=obj.object_type,
                    object_context=object_context,
                )
            for field_name, obj in sorted(table.metrics.items()):
                table_payload["metrics"][field_name] = {
                    "expr": obj.expr,
                    "ai_context": obj.ai_context or {},
                }
                object_context = obj.ai_context or {}
                _register_field_concept(
                    concepts,
                    fields,
                    view_name=view_name,
                    table_name=table_name,
                    field_name=field_name,
                    field_kind="metric",
                    object_context=object_context,
                )
            for field_name, obj in sorted(table.facts.items()):
                table_payload["facts"][field_name] = {
                    "expr": obj.expr,
                    "ai_context": obj.ai_context or {},
                }
            view_payload["tables"][table_name] = table_payload

        _register_scope_concepts(
            concepts,
            fields,
            view_name=view_name,
            time_dimensions=time_dimensions,
            scope_context=registry.ai_context,
        )
        for table_name, table in sorted(registry.tables.items()):
            _register_scope_concepts(
                concepts,
                fields,
                view_name=view_name,
                time_dimensions=[item for item in time_dimensions if item[0] == table_name],
                scope_context=table.ai_context,
            )
        if time_dimensions:
            for index, (table_name, field_name) in enumerate(time_dimensions):
                fields.append(
                    SemanticConceptField(
                        concept_id="recent",
                        concept_kind="modifier",
                        view_name=view_name,
                        table_name=table_name,
                        field_name=field_name,
                        field_kind="time_dimension",
                        is_preferred=index == 0,
                    )
                )
        fingerprint_payload["views"][view_name] = view_payload

    fingerprint = compute_fingerprint(fingerprint_payload)
    deduped_fields: list[SemanticConceptField] = []
    seen_field_keys: set[tuple[str, str, str, str, str]] = set()
    for field in fields:
        key = (field.concept_id, field.concept_kind, field.view_name, field.field_name, field.field_kind)
        if key in seen_field_keys:
            continue
        seen_field_keys.add(key)
        deduped_fields.append(field)
    return SemanticConceptIndex(
        fingerprint=fingerprint,
        concepts=sorted(concepts.values(), key=lambda item: (item.concept_kind, item.concept_id)),
        fields=sorted(
            deduped_fields,
            key=lambda item: (item.view_name, item.concept_kind, item.concept_id, item.field_name),
        ),
    )
