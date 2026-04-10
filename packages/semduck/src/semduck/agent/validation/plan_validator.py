from __future__ import annotations

from typing import Any

from .intent_parser import infer_intent
from .models import PlanValidationResult, ValidationIssue
from .policy import DEFAULT_VALIDATION_POLICY, ValidationPolicy
from .retry_builder import build_retry_feedback
from .schema_index import build_schema_index, views_covering


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


def _selected_dimension_names(plan: Any, policy: ValidationPolicy) -> set[str]:
    names: set[str] = set()
    for item in plan.dimensions:
        transformed = _match_time_transform(item, policy)
        if transformed is not None:
            _, field, _ = transformed
            names.add(field)
            continue
        names.add(item)
    return names


def _selected_sort_name(plan: Any) -> str | None:
    if not plan.order_by:
        return None
    candidate = plan.order_by[0].strip()
    tokens = candidate.rsplit(" ", 1)
    if len(tokens) == 2 and tokens[1].lower() in {"asc", "desc"}:
        return tokens[0].strip()
    return candidate


def _normalize_time_bucket_aliases(
    plan: Any,
    chosen_view: Any | None,
    *,
    add_issue,
) -> Any:
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
        if replacement is not None:
            normalized_order_by.append(f"{replacement}{suffix}")
        else:
            normalized_order_by.append(item)
    normalized.order_by = normalized_order_by
    return normalized


def validate_plan(
    question: str,
    plan: Any,
    conn,
    *,
    policy: ValidationPolicy = DEFAULT_VALIDATION_POLICY,
) -> PlanValidationResult:
    index = build_schema_index(conn)
    intent = infer_intent(question, index, policy=policy)
    candidate_views = views_covering(
        index,
        dimensions=intent.required_dimensions,
        metrics=intent.required_metrics,
    )
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
        if intent.required_dimensions or intent.required_metrics:
            add_issue(
                "no_single_view_covers_request",
                "No single described semantic view contains all required dimensions and metrics.",
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

    chosen_view = next((view for view in index.views if view.view_name == normalized_plan.chosen_view), None)
    if chosen_view is None:
        add_issue(
            "unknown_view",
            f"Unknown semantic view: {normalized_plan.chosen_view}",
            field="chosen_view",
            details={"chosen_view": normalized_plan.chosen_view},
        )
    else:
        normalized_plan = _normalize_time_bucket_aliases(
            normalized_plan,
            chosen_view,
            add_issue=add_issue,
        )
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

    if not candidate_views and (intent.required_dimensions or intent.required_metrics):
        add_issue(
            "unsupported_question",
            "No single semantic view covers the required concepts from the question.",
        )
        add_issue(
            "no_single_view_covers_request",
            "No single described semantic view contains all required dimensions and metrics.",
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

    selected_dimensions = _selected_dimension_names(normalized_plan, policy)
    for required_metric in intent.required_metrics:
        if required_metric not in normalized_plan.metrics:
            selected_metric = normalized_plan.metrics[0] if normalized_plan.metrics else None
            add_issue(
                "forbidden_metric_substitution" if selected_metric else "missing_metric",
                f"Question requires metric {required_metric}.",
                field="metrics",
                details={
                    "required_metric": required_metric,
                    "selected_metric": selected_metric,
                },
            )

    for required_dimension in intent.required_dimensions:
        if required_dimension not in selected_dimensions:
            add_issue(
                "forbidden_dimension_substitution",
                f"Question requires dimension {required_dimension}.",
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
        elif intent.sort_metric is not None and _selected_sort_name(normalized_plan) != intent.sort_metric:
            add_issue(
                "missing_order_by_for_ranking",
                f"Ranking questions should order by {intent.sort_metric}.",
                field="order_by",
            )

    if intent.required_time_grain is not None:
        matching_time_bucket = False
        for item in normalized_plan.dimensions:
            transformed = _match_time_transform(item, policy)
            if transformed is None:
                continue
            grain, field, _ = transformed
            time_dimension_matches = True
            if intent.required_time_dimension_confident and intent.required_time_dimension is not None:
                time_dimension_matches = field == intent.required_time_dimension
            if grain == intent.required_time_grain and time_dimension_matches:
                matching_time_bucket = True
                break
        if not matching_time_bucket:
            add_issue(
                "missing_time_grain",
                f"Question requires a {intent.required_time_grain} time bucket.",
                field="dimensions",
                details={
                    "grain": intent.required_time_grain,
                    "time_dimension": intent.required_time_dimension,
                    "time_dimension_confident": intent.required_time_dimension_confident,
                },
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
