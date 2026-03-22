from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RequestedDimension:
    pass


@dataclass
class NamedDimension(RequestedDimension):
    name: str


@dataclass
class DerivedDimension(RequestedDimension):
    expr: str
    alias: str


@dataclass
class RequestedMetric:
    pass


@dataclass
class NamedMetric(RequestedMetric):
    name: str


@dataclass
class DerivedMetric(RequestedMetric):
    expr: str
    alias: str


@dataclass
class ParsedSemanticRequest:
    semantic_view_ref: str
    dimensions: list[RequestedDimension] = field(default_factory=list)
    metrics: list[RequestedMetric] = field(default_factory=list)
    where_clause: Optional[str] = None


@dataclass
class SemanticObject:
    name: str
    object_type: str
    expr: str
    data_type: Optional[str] = None
    table_name: Optional[str] = None
    default_agg: Optional[str] = None
    metric_type: Optional[str] = None


@dataclass
class SemanticTable:
    name: str
    physical_schema: Optional[str]
    physical_table: str
    alias: str
    dimensions: dict[str, SemanticObject]
    metrics: dict[str, SemanticObject]
    facts: dict[str, SemanticObject]


@dataclass
class SemanticJoin:
    left_table: str
    right_table: str
    join_type: str
    join_expr: str


@dataclass
class SemanticViewRegistry:
    view_name: str
    tables: dict[str, SemanticTable]
    joins: list[SemanticJoin]


@dataclass
class ResolvedDimension:
    request_name: str
    table_name: str
    alias: str
    expr_sql: str
    object_type: str


@dataclass
class ResolvedMetric:
    request_name: str
    table_name: str
    alias: str
    expr_sql: str
    metric_type: str


@dataclass
class ResolvedDerivedDimension:
    alias: str
    expr_sql: str


@dataclass
class ResolvedDerivedMetric:
    alias: str
    expr_sql: str


@dataclass
class QueryPlan:
    semantic_view_ref: str
    from_table: str
    from_alias: str
    joins: list[SemanticJoin]
    dimensions: list[ResolvedDimension]
    metrics: list[ResolvedMetric]
    derived_dimensions: list[ResolvedDerivedDimension]
    derived_metrics: list[ResolvedDerivedMetric]
    output_dimensions: list[str]
    output_metrics: list[str]
    where_clause: Optional[str]


@dataclass
class LoadResult:
    ok: bool
    view_name: str
    validated_only: bool


@dataclass
class CompiledSemanticQuery:
    request: str
    parsed_request: ParsedSemanticRequest
    plan: QueryPlan
    sql: str
