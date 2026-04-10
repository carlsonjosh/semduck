from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True)
class ValidationPolicy:
    metric_aliases: dict[str, list[str]] = field(default_factory=dict)
    dimension_aliases: dict[str, list[str]] = field(default_factory=dict)
    time_defaults: dict[str, str] = field(default_factory=dict)
    intent_keywords: dict[str, tuple[str, ...]] = field(default_factory=dict)
    allowed_dimension_transform_patterns: tuple[re.Pattern[str], ...] = field(default_factory=tuple)


DEFAULT_VALIDATION_POLICY = ValidationPolicy(
    metric_aliases={
        "product revenue": ["net_item_sales"],
        "item revenue": ["net_item_sales"],
        "net item sales": ["net_item_sales"],
        "gross item sales": ["gross_item_sales"],
        "net sales": ["net_sales"],
        "shipping revenue": ["total_shipping"],
        "tax": ["total_tax"],
        "average order value": ["average_order_value"],
        "lifetime value": ["lifetime_value"],
        "customer count": ["customer_count"],
        "total revenue": ["total_revenue"],
        "order count": ["order_count"],
        "units sold": ["units_sold"],
    },
    dimension_aliases={
        "sales channel": ["sales_channel"],
        "payment method": ["payment_method"],
        "payment methods": ["payment_method"],
        "segment": ["segment_name"],
        "segments": ["segment_name"],
        "customer segment": ["customer_segment"],
        "signup cohort": ["signup_date"],
        "acquisition cohort": ["signup_date"],
        "signup month": ["signup_date"],
        "marketing campaign": ["marketing_campaign"],
        "marketing campaigns": ["marketing_campaign"],
        "customer state": ["customer_state"],
        "state": ["customer_state"],
        "states": ["customer_state"],
        "region": ["region"],
        "month": [],
        "quarter": [],
        "year": [],
        "week": [],
        "day": [],
    },
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
)
