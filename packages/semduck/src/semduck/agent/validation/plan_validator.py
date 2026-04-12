from __future__ import annotations

from typing import Any

from .concept_store import ensure_semantic_concepts
from .concepts import view_field_lookup
from .intent_builder import resolve_question_intent
from .models import PlanValidationResult, SemanticConceptIndex, ValidationIssue
from .policy import DEFAULT_VALIDATION_POLICY, ValidationPolicy
from .retry_builder import build_retry_feedback
from .schema_index import build_schema_index


def _derived_time_alias(field: str, grain: str) -> str:
    if field.endswith("_date"):
        return f"{field[:-5]}_{grain}"
    return f"{field}_{grain}"


def _match_time_transform(item: str, policy: ValidationPolicy) -> tuple[str, str, str] | None:
    for pattern in policy.allowed_dimension_transform_patterns:
        match = pattern.fullmatch(item.strip())
        if match is not None:
            return (
                match.group("grain").lower(),
                match.group("field"),
                match.group("alias"),
            )
    return None


def _match_unaliased_time_transform(item: str) -> tuple[str, str] | None:
    import re

    match = re.fullmatch(
        r"date_trunc\('(?P<grain>day|week|month|quarter|year)',\s*(?P<field>[A-Za-z_][A-Za-z0-9_]*)\)",
        item.strip(),
        re.IGNORECASE,
    )
    if match is None:
        return None
    return match.group("grain").lower(), match.group("field")


def _selected_sort_name(plan: Any) -> str | None:
    if not plan.order_by:
        return None
    candidate = plan.order_by[0].strip()
    tokens = candidate.rsplit(" ", 1)
    if len(tokens) == 2 and tokens[1].lower() in {"asc", "desc"}:
        return tokens[0].strip()
    return candidate


def _normalize_time_bucket_aliases(plan: Any, chosen_view: Any | None, *, add_issue) -> Any:
    if chosen_view is None:
        return plan

    normalized = plan.model_copy(deep=True)
    replacements: dict[str, str] = {}
    normalized_dimensions: list[str] = []
    for item in normalized.dimensions:
        unaliased = _match_unaliased_time_transform(item)
        if unaliased is None:
            normalized_dimensions.append(item)
            continue
        grain, field = unaliased
        if field not in chosen_view.time_dimensions:
            normalized_dimensions.append(item)
            continue
        alias = _derived_time_alias(field, grain)
        rewritten = f"date_trunc('{grain}', {field}) as {alias}"
        replacements[item.strip()] = alias
        normalized_dimensions.append(rewritten)
        add_issue(
            "normalized_time_bucket_alias",
            f"Normalized {item} to {rewritten}.",
            field="dimensions",
            details={"original_dimension": item, "normalized_dimension": rewritten},
            severity="warning",
        )
    normalized.dimensions = normalized_dimensions

    normalized_order_by: list[str] = []
    for item in normalized.order_by:
        candidate = item.strip()
        tokens = candidate.rsplit(" ", 1)
        suffix = ""
        expression = candidate
        if len(tokens) == 2 and tokens[1].lower() in {"asc", "desc"}:
            expression = tokens[0].strip()
            suffix = f" {tokens[1].lower()}"
        replacement = replacements.get(expression)
        normalized_order_by.append(f"{replacement}{suffix}" if replacement is not None else item)
    normalized.order_by = normalized_order_by
    return normalized


def _candidate_views(index: SemanticConceptIndex, intent) -> list[str]:
    required = (
        {(concept_id, "dimension") for concept_id in intent.required_dimensions}
        .union((concept_id, "metric") for concept_id in intent.required_metrics)
        .union((concept_id, "modifier") for concept_id in intent.required_modifiers)
    )
    if not required:
        return sorted({field.view_name for field in index.fields})
    per_view: dict[str, set[tuple[str, str]]] = {}
    for field in index.fields:
        per_view.setdefault(field.view_name, set()).add((field.concept_id, field.concept_kind))
    return sorted(view_name for view_name, concepts in per_view.items() if required.issubset(concepts))


def _selected_concepts(plan: Any, chosen_view_name: str, index: SemanticConceptIndex, policy: ValidationPolicy) -> tuple[set[str], set[str]]:
    lookup = view_field_lookup(index).get(chosen_view_name, {})
    selected_dimensions: set[str] = set()
    selected_metrics: set[str] = set()

    for metric in plan.metrics:
        for field in lookup.get(metric, []):
            if field.concept_kind == "metric":
                selected_metrics.add(field.concept_id)

    for item in plan.dimensions:
        transformed = _match_time_transform(item, policy)
        field_name = transformed[1] if transformed is not None else item
        for field in lookup.get(field_name, []):
            if field.concept_kind == "dimension":
                selected_dimensions.add(field.concept_id)
            elif field.concept_kind == "modifier":
                selected_dimensions.add(field.concept_id)
    return selected_dimensions, selected_metrics


def _preferred_recent_field(index: SemanticConceptIndex, view_name: str) -> str | None:
    candidates = [
        field
        for field in index.fields
        if field.view_name == view_name and field.concept_id == "recent"
    ]
    if not candidates:
        return None
    preferred = next((field for field in candidates if field.is_preferred), None)
    return (preferred or candidates[0]).field_name


def validate_plan(
    question: str,
    plan: Any,
    conn,
    *,
    policy: ValidationPolicy = DEFAULT_VALIDATION_POLICY,
) -> PlanValidationResult:
    schema_index = build_schema_index(conn)
    concept_index = ensure_semantic_concepts(conn, policy)
    intent = resolve_question_intent(question, concept_index, policy=policy)
    candidate_views = _candidate_views(concept_index, intent)
    issues: list[ValidationIssue] = []
    normalized_plan = plan.model_copy(deep=True)

    def add_issue(
        code: str,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
        severity: str = "error",
    ) -> None:
        issues.append(
            ValidationIssue(
                code=code,
                severity=severity,
                message=message,
                field=field,
                details=details or {},
            )
        )

    if normalized_plan.chosen_view is None:
        if len(candidate_views) == 1:
            add_issue(
                "false_unsupported_candidate_exists",
                "Planner returned null plan even though a single matching semantic view exists.",
                details={"candidate_view": candidate_views[0]},
            )
            result = PlanValidationResult(
                is_valid=False,
                issues=issues,
                normalized_plan=normalized_plan,
                action="reject_for_retry",
                intent=intent,
                candidate_views=candidate_views,
            )
            result.retry_feedback = build_retry_feedback(result)
            return result
        add_issue(
            "unsupported_question",
            "The available semantic views cannot answer this question without substitution.",
        )
        if intent.required_dimensions or intent.required_metrics or intent.required_modifiers:
            add_issue(
                "no_single_view_covers_request",
                "No single described semantic view contains all required concepts.",
            )
        result = PlanValidationResult(
            is_valid=False,
            issues=issues,
            normalized_plan=normalized_plan,
            action="reject_as_unsupported",
            intent=intent,
            candidate_views=candidate_views,
        )
        result.retry_feedback = build_retry_feedback(result)
        return result

    chosen_view = next((view for view in schema_index.views if view.view_name == normalized_plan.chosen_view), None)
    if chosen_view is None:
        add_issue(
            "unknown_view",
            f"Unknown semantic view: {normalized_plan.chosen_view}",
            field="chosen_view",
            details={"chosen_view": normalized_plan.chosen_view},
        )
    else:
        normalized_plan = _normalize_time_bucket_aliases(normalized_plan, chosen_view, add_issue=add_issue)
        for metric in normalized_plan.metrics:
            if metric not in chosen_view.metrics:
                add_issue(
                    "missing_metric",
                    f"Metric {metric} is not available in {chosen_view.view_name}.",
                    field="metrics",
                    details={"metric": metric, "chosen_view": chosen_view.view_name},
                )
        for dimension in normalized_plan.dimensions:
            transformed = _match_time_transform(dimension, policy)
            if transformed is not None:
                _, field, _ = transformed
                if field not in chosen_view.time_dimensions:
                    add_issue(
                        "missing_time_grain",
                        f"Time transform references unknown time dimension {field}.",
                        field="dimensions",
                        details={"time_dimension": field, "chosen_view": chosen_view.view_name},
                    )
                continue
            if dimension not in chosen_view.dimensions:
                add_issue(
                    "missing_dimension",
                    f"Dimension {dimension} is not available in {chosen_view.view_name}.",
                    field="dimensions",
                    details={"dimension": dimension, "chosen_view": chosen_view.view_name},
                )
        if candidate_views and chosen_view.view_name not in candidate_views and len(candidate_views) == 1:
            add_issue(
                "false_unsupported_candidate_exists",
                "A different single semantic view satisfies the required concepts.",
                details={"candidate_view": candidate_views[0]},
            )

    if not candidate_views and (intent.required_dimensions or intent.required_metrics or intent.required_modifiers):
        add_issue(
            "unsupported_question",
            "No single semantic view covers the required concepts from the question.",
        )
        add_issue(
            "no_single_view_covers_request",
            "No single described semantic view contains all required concepts.",
        )
        result = PlanValidationResult(
            is_valid=False,
            issues=issues,
            normalized_plan=normalized_plan,
            action="reject_as_unsupported",
            intent=intent,
            candidate_views=candidate_views,
        )
        result.retry_feedback = build_retry_feedback(result)
        return result

    selected_dimensions, selected_metrics = _selected_concepts(
        normalized_plan,
        normalized_plan.chosen_view,
        concept_index,
        policy,
    )
    for required_metric in intent.required_metrics:
        if required_metric not in selected_metrics:
            selected_metric = normalized_plan.metrics[0] if normalized_plan.metrics else None
            add_issue(
                "forbidden_metric_substitution" if selected_metric else "missing_metric",
                f"Question requires metric concept {required_metric}.",
                field="metrics",
                details={"required_metric": required_metric, "selected_metric": selected_metric},
            )

    for required_dimension in intent.required_dimensions:
        if required_dimension not in selected_dimensions:
            add_issue(
                "forbidden_dimension_substitution",
                f"Question requires dimension concept {required_dimension}.",
                field="dimensions",
                details={"required_dimension": required_dimension},
            )

    if intent.requires_sort:
        if not normalized_plan.order_by:
            add_issue(
                "missing_order_by_for_ranking",
                "Ranking questions require order_by.",
                field="order_by",
            )
        elif intent.sort_metric is not None:
            selected_sort = _selected_sort_name(normalized_plan)
            sort_concepts = {
                field.concept_id
                for field in view_field_lookup(concept_index).get(normalized_plan.chosen_view, {}).get(selected_sort or "", [])
                if field.concept_kind == "metric"
            }
            if intent.sort_metric not in sort_concepts and selected_sort != intent.sort_metric:
                add_issue(
                    "missing_order_by_for_ranking",
                    f"Ranking questions should order by the {intent.sort_metric} concept.",
                    field="order_by",
                )

    if intent.required_time_grain is not None:
        matching_time_bucket = False
        for item in normalized_plan.dimensions:
            transformed = _match_time_transform(item, policy)
            if transformed is None:
                continue
            grain, field, _ = transformed
            if grain == intent.required_time_grain:
                if not intent.required_time_dimension_confident or intent.required_time_dimension is None:
                    matching_time_bucket = True
                    break
                dimension_lookup = view_field_lookup(concept_index).get(normalized_plan.chosen_view, {}).get(field, [])
                if any(binding.concept_id == intent.required_time_dimension for binding in dimension_lookup):
                    matching_time_bucket = True
                    break
        if not matching_time_bucket:
            add_issue(
                "missing_time_grain",
                f"Question requires a {intent.required_time_grain} time bucket.",
                field="dimensions",
                details={"grain": intent.required_time_grain, "time_dimension": intent.required_time_dimension},
            )

    if "recent" in intent.required_modifiers:
        recent_field = _preferred_recent_field(concept_index, normalized_plan.chosen_view)
        where_clause = (normalized_plan.where_clause or "").lower()
        if recent_field is None or recent_field.lower() not in where_clause:
            add_issue(
                "missing_recent_filter",
                "Question requires a recent time filter.",
                field="where_clause",
                details={"time_dimension": recent_field, "window": intent.recent_window},
            )

    has_errors = any(issue.severity == "error" for issue in issues)
    if has_errors:
        action = "reject_for_retry"
        if any(issue.code in {"unsupported_question", "no_single_view_covers_request"} for issue in issues):
            action = "reject_as_unsupported"
        result = PlanValidationResult(
            is_valid=False,
            issues=issues,
            normalized_plan=normalized_plan,
            action=action,
            intent=intent,
            candidate_views=candidate_views,
        )
        result.retry_feedback = build_retry_feedback(result)
        return result

    result = PlanValidationResult(
        is_valid=True,
        issues=issues,
        normalized_plan=normalized_plan,
        action="accept",
        intent=intent,
        candidate_views=candidate_views,
    )
    result.retry_feedback = build_retry_feedback(result)
    return result
