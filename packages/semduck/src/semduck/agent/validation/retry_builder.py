from __future__ import annotations

from .models import PlanValidationResult, ValidationIssue


def _feedback_for_issue(issue: ValidationIssue) -> str:
    details = issue.details
    if issue.code == "unknown_view":
        return f"Selected view {details.get('chosen_view', issue.field)} is not a known semantic view."
    if issue.code == "missing_metric":
        return f"Selected view {details.get('chosen_view')} does not contain metric {details.get('metric')}."
    if issue.code == "missing_dimension":
        return f"Selected view {details.get('chosen_view')} does not contain dimension {details.get('dimension')}."
    if issue.code == "forbidden_metric_substitution":
        return (
            f"Question requires metric {details.get('required_metric')}, "
            f"but the plan selected {details.get('selected_metric')}."
        )
    if issue.code == "forbidden_dimension_substitution":
        return (
            f"Question requires dimension {details.get('required_dimension')}, "
            f"but the plan did not preserve it."
        )
    if issue.code == "missing_order_by_for_ranking":
        return "Question requests ranking, so order_by must sort the selected metric."
    if issue.code == "missing_time_grain":
        return (
            f"Question requires a {details.get('grain')} time bucket on "
            f"{details.get('time_dimension')}."
        )
    if issue.code == "false_unsupported_candidate_exists":
        return f"A valid single-view candidate exists: {details.get('candidate_view')}."
    if issue.code == "no_single_view_covers_request":
        return "No single described semantic view contains all required dimensions and metrics."
    if issue.code == "unsupported_question":
        return issue.message
    return issue.message


def build_retry_feedback(result: PlanValidationResult) -> list[str]:
    feedback: list[str] = []
    for issue in result.issues:
        if issue.severity != "error":
            continue
        line = _feedback_for_issue(issue)
        if line and line not in feedback:
            feedback.append(line)
    return feedback
