from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ValidationSeverity = Literal["error", "warning"]
ValidationAction = Literal[
    "accept",
    "reject_as_unsupported",
    "reject_for_retry",
    "reject_execution",
    "accept_with_warnings",
]
QuestionType = Literal[
    "trend",
    "ranking",
    "comparison",
    "breakdown",
    "cohort",
    "rollup",
    "unsupported",
]


class ValidationIssue(BaseModel):
    code: str
    severity: ValidationSeverity
    message: str
    field: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class IntentSpec(BaseModel):
    question_type: QuestionType
    required_dimensions: list[str] = Field(default_factory=list)
    required_metrics: list[str] = Field(default_factory=list)
    required_modifiers: list[str] = Field(default_factory=list)
    required_time_dimension: str | None = None
    required_time_dimension_confident: bool = False
    required_time_grain: str | None = None
    requires_sort: bool = False
    sort_metric: str | None = None
    chronological: bool = False
    recent_window: str | None = None


class ViewCoverage(BaseModel):
    view_name: str
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    time_dimensions: list[str] = Field(default_factory=list)


class SchemaIndex(BaseModel):
    views: list[ViewCoverage] = Field(default_factory=list)
    all_dimensions: list[str] = Field(default_factory=list)
    all_metrics: list[str] = Field(default_factory=list)


class PlanValidationResult(BaseModel):
    is_valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    normalized_plan: Any | None = None
    action: ValidationAction
    intent: IntentSpec | None = None
    candidate_views: list[str] = Field(default_factory=list)
    retry_feedback: list[str] = Field(default_factory=list)


class SemanticConcept(BaseModel):
    concept_id: str
    concept_kind: str
    phrases: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticConceptField(BaseModel):
    concept_id: str
    concept_kind: str
    view_name: str
    table_name: str | None = None
    field_name: str
    field_kind: str
    is_preferred: bool = False


class SemanticConceptIndex(BaseModel):
    fingerprint: str
    concepts: list[SemanticConcept] = Field(default_factory=list)
    fields: list[SemanticConceptField] = Field(default_factory=list)
