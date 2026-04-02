from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


DefinitionFormat = Literal["auto", "yaml", "ddl"]


class ServiceErrorDetail(BaseModel):
    code: str
    message: str


class InitRegistryArgs(BaseModel):
    pass


class InitRegistryResult(BaseModel):
    ok: bool = True


class CheckDefinitionArgs(BaseModel):
    file: str
    format: DefinitionFormat = "auto"


class CheckDefinitionResult(BaseModel):
    ok: bool
    view_name: str
    validated_only: bool
    format: Literal["yaml", "ddl"]


class LoadDefinitionArgs(BaseModel):
    file: str
    format: DefinitionFormat = "auto"
    replace_existing: bool = True


class LoadDefinitionResult(BaseModel):
    ok: bool
    view_name: str
    validated_only: bool
    format: Literal["yaml", "ddl"]


class CompileRequestArgs(BaseModel):
    request: str


class CompileRequestResult(BaseModel):
    request: str
    semantic_view_ref: str
    sql: str


class QueryRequestArgs(BaseModel):
    request: str


class QueryRequestResult(BaseModel):
    request: str
    semantic_view_ref: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]


class ListSemanticViewsArgs(BaseModel):
    pass


class ListSemanticViewsResult(BaseModel):
    view_names: list[str]


class DescribeSemanticViewArgs(BaseModel):
    view_name: str


class SemanticObjectDescriptor(BaseModel):
    name: str
    object_type: str
    expr: str
    data_type: str | None = None
    default_agg: str | None = None
    metric_type: str | None = None


class SemanticTableDescriptor(BaseModel):
    name: str
    physical_schema: str | None
    physical_table: str
    alias: str
    dimensions: list[SemanticObjectDescriptor]
    metrics: list[SemanticObjectDescriptor]
    facts: list[SemanticObjectDescriptor]


class SemanticJoinDescriptor(BaseModel):
    left_table: str
    right_table: str
    join_type: str
    join_expr: str


class SemanticViewDescriptor(BaseModel):
    view_name: str
    tables: list[SemanticTableDescriptor]
    joins: list[SemanticJoinDescriptor]
