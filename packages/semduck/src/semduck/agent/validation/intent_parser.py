from __future__ import annotations

import re

from .models import IntentSpec
from .policy import DEFAULT_VALIDATION_POLICY, ValidationPolicy
from .schema_index import SchemaIndex


def _contains_phrase(question: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", question) is not None


def _find_phrase_span(question: str, phrase: str) -> tuple[int, int] | None:
    match = re.search(rf"\b{re.escape(phrase)}\b", question)
    if match is None:
        return None
    return match.span()


def _field_phrases(name: str) -> set[str]:
    humanized = name.replace("_", " ")
    phrases = {name.lower(), humanized.lower()}
    if humanized.endswith("y"):
        phrases.add(f"{humanized[:-1]}ies")
    else:
        phrases.add(f"{humanized}s")
    return phrases


def _collect_unambiguous_field_matches(
    question: str,
    fields: list[str],
    *,
    consumed_spans: list[tuple[int, int]] | None = None,
) -> list[str]:
    phrase_to_fields: dict[str, set[str]] = {}
    for field in fields:
        for phrase in _field_phrases(field):
            phrase_to_fields.setdefault(phrase, set()).add(field)

    matches: list[str] = []
    for phrase, matched_fields in phrase_to_fields.items():
        if len(matched_fields) != 1:
            continue
        field = next(iter(matched_fields))
        span = _find_phrase_span(question, phrase)
        if span is None:
            continue
        if consumed_spans is not None and any(not (span[1] <= start or span[0] >= end) for start, end in consumed_spans):
            continue
        if _contains_phrase(question, phrase) and field not in matches:
            matches.append(field)
    return matches


def infer_intent(
    question: str,
    schema_index: SchemaIndex,
    *,
    policy: ValidationPolicy = DEFAULT_VALIDATION_POLICY,
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

    required_metrics: list[str] = []
    consumed_metric_spans: list[tuple[int, int]] = []
    for phrase, allowed_metrics in sorted(policy.metric_aliases.items(), key=lambda item: len(item[0]), reverse=True):
        span = _find_phrase_span(lowered, phrase)
        if span is None:
            continue
        if any(not (span[1] <= start or span[0] >= end) for start, end in consumed_metric_spans):
            continue
        consumed_metric_spans.append(span)
        if _contains_phrase(lowered, phrase):
            for metric in allowed_metrics:
                if metric not in required_metrics:
                    required_metrics.append(metric)

    for metric in _collect_unambiguous_field_matches(
        lowered,
        schema_index.all_metrics,
        consumed_spans=consumed_metric_spans,
    ):
        if metric not in required_metrics:
            required_metrics.append(metric)

    required_dimensions: list[str] = []
    consumed_dimension_spans: list[tuple[int, int]] = []
    for phrase, canonical_dimensions in sorted(policy.dimension_aliases.items(), key=lambda item: len(item[0]), reverse=True):
        span = _find_phrase_span(lowered, phrase)
        if span is None:
            continue
        if any(not (span[1] <= start or span[0] >= end) for start, end in consumed_dimension_spans):
            continue
        consumed_dimension_spans.append(span)
        if _contains_phrase(lowered, phrase):
            for dimension in canonical_dimensions:
                if dimension not in required_dimensions:
                    required_dimensions.append(dimension)

    for dimension in _collect_unambiguous_field_matches(
        lowered,
        schema_index.all_dimensions,
        consumed_spans=consumed_dimension_spans,
    ):
        if dimension not in required_dimensions:
            required_dimensions.append(dimension)

    required_time_grain = None
    required_time_dimension = None
    required_time_dimension_confident = False
    for grain in ("day", "week", "month", "quarter", "year"):
        if re.search(rf"\b{grain}\b", lowered):
            required_time_grain = grain
            break

    if question_type in {"trend", "cohort"} and required_time_grain is None:
        required_time_grain = policy.time_defaults.get(question_type)

    if question_type == "cohort":
        required_time_dimension = "signup_date"
        required_time_dimension_confident = True
        if "signup_date" not in required_dimensions:
            required_dimensions.append("signup_date")
    elif required_time_grain is not None:
        for dimension in required_dimensions:
            if dimension in {"signup_date", "order_date"}:
                required_time_dimension = dimension
                required_time_dimension_confident = True
                break
        preferred_dimension_order = [
            "order_date",
            "signup_date",
            *schema_index.all_dimensions,
        ]
        if required_time_dimension is None:
            for dimension in preferred_dimension_order:
                if dimension in required_dimensions and dimension in schema_index.all_dimensions:
                    required_time_dimension = dimension
                    required_time_dimension_confident = True
                    break
        if required_time_dimension is None:
            for dimension in preferred_dimension_order:
                if dimension in schema_index.all_dimensions:
                    required_time_dimension = dimension
                    break

    requires_sort = question_type == "ranking"
    sort_metric = required_metrics[0] if requires_sort and required_metrics else None

    return IntentSpec(
        question_type=question_type,
        required_dimensions=required_dimensions,
        required_metrics=required_metrics,
        required_time_dimension=required_time_dimension,
        required_time_dimension_confident=required_time_dimension_confident,
        required_time_grain=required_time_grain,
        requires_sort=requires_sort,
        sort_metric=sort_metric,
        chronological=question_type in {"trend", "cohort"},
    )
