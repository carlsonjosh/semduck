from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True)
class ValidationPolicy:
    policy_version: str = "ai_context_v1"
    time_defaults: dict[str, str] = field(default_factory=dict)
    intent_keywords: dict[str, tuple[str, ...]] = field(default_factory=dict)
    allowed_dimension_transform_patterns: tuple[re.Pattern[str], ...] = field(default_factory=tuple)
    default_recent_window: str = "30 days"
    generic_modifier_concepts: tuple[dict[str, object], ...] = field(default_factory=tuple)


DEFAULT_VALIDATION_POLICY = ValidationPolicy(
    time_defaults={
        "trend": "month",
        "cohort": "month",
    },
    intent_keywords={
        "ranking": ("top", "most", "highest", "rank", "lowest", "best"),
        "trend": ("trend", "over time", "by month", "by quarter", "by year", "by week", "by day"),
        "cohort": ("cohort", "signup cohort", "acquisition cohort"),
    },
    allowed_dimension_transform_patterns=(
        re.compile(
            r"^date_trunc\('(?P<grain>day|week|month|quarter|year)',\s*(?P<field>[A-Za-z_][A-Za-z0-9_]*)\)\s+as\s+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)$",
            re.IGNORECASE,
        ),
    ),
    generic_modifier_concepts=(
        {
            "concept_id": "recent",
            "concept_kind": "modifier",
            "phrases": ("recent", "recently", "latest period", "latest periods"),
            "default_window": "30 days",
        },
    ),
)
