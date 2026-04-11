from __future__ import annotations

import re

from .concepts import concept_lookup
from .models import IntentSpec, SemanticConceptIndex
from .policy import ValidationPolicy


def _contains_phrase(question: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", question) is not None


def resolve_question_intent(
    question: str,
    concept_index: SemanticConceptIndex,
    *,
    policy: ValidationPolicy,
) -> IntentSpec:
    lowered = question.lower()
    if any(keyword in lowered for keyword in policy.intent_keywords["cohort"]):
        question_type = "cohort"
    elif any(keyword in lowered for keyword in policy.intent_keywords["ranking"]):
        question_type = "ranking"
    elif any(keyword in lowered for keyword in policy.intent_keywords["trend"]):
        question_type = "trend"
    elif "compare" in lowered or "versus" in lowered or "vs " in lowered:
        question_type = "comparison"
    elif " by " in lowered or " each " in lowered or " combination" in lowered:
        question_type = "breakdown"
    else:
        question_type = "rollup"

    required_dimensions: list[str] = []
    required_metrics: list[str] = []
    required_modifiers: list[str] = []
    for concept in sorted(concept_index.concepts, key=lambda item: max((len(phrase) for phrase in item.phrases), default=0), reverse=True):
        if not any(_contains_phrase(lowered, phrase) for phrase in concept.phrases):
            continue
        if concept.concept_kind == "metric" and concept.concept_id not in required_metrics:
            required_metrics.append(concept.concept_id)
        elif concept.concept_kind == "dimension" and concept.concept_id not in required_dimensions:
            required_dimensions.append(concept.concept_id)
        elif concept.concept_kind not in {"metric", "dimension"} and concept.concept_id not in required_modifiers:
            required_modifiers.append(concept.concept_id)

    required_time_grain = None
    for grain in ("day", "week", "month", "quarter", "year"):
        if re.search(rf"\b{grain}\b", lowered):
            required_time_grain = grain
            break
    if question_type in {"trend", "cohort"} and required_time_grain is None:
        required_time_grain = policy.time_defaults.get(question_type)

    required_time_dimension = None
    required_time_dimension_confident = False
    for concept_id in required_dimensions:
        if concept_id.endswith("_date"):
            required_time_dimension = concept_id
            required_time_dimension_confident = True
            break

    recent_window = None
    if "recent" in required_modifiers:
        recent_concept = concept_lookup(concept_index).get(("recent", "modifier"))
        if recent_concept is not None:
            recent_window = str(recent_concept.metadata.get("default_window") or policy.default_recent_window)

    return IntentSpec(
        question_type=question_type,
        required_dimensions=required_dimensions,
        required_metrics=required_metrics,
        required_modifiers=required_modifiers,
        required_time_dimension=required_time_dimension,
        required_time_dimension_confident=required_time_dimension_confident,
        required_time_grain=required_time_grain,
        requires_sort=question_type == "ranking",
        sort_metric=required_metrics[0] if question_type == "ranking" and required_metrics else None,
        chronological=question_type in {"trend", "cohort"},
        recent_window=recent_window,
    )
