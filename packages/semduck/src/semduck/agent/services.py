from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from semduck.api import (
    compile_request,
    get_semantic_view,
    init_registry,
    list_semantic_views,
    load_semantic_ddl_file,
    load_semantic_yaml_file,
)
from semduck.errors import SemanticViewError
from semduck.types import CompiledSemanticQuery, LoadResult, SemanticObject, SemanticTable, SemanticViewRegistry

from .models import (
    CheckDefinitionArgs,
    CheckDefinitionResult,
    CompileRequestArgs,
    CompileRequestResult,
    DescribeSemanticViewArgs,
    InitRegistryArgs,
    InitRegistryResult,
    ListSemanticViewsArgs,
    ListSemanticViewsResult,
    LoadDefinitionArgs,
    LoadDefinitionResult,
    QueryRequestArgs,
    QueryRequestResult,
    SemanticJoinDescriptor,
    SemanticObjectDescriptor,
    SemanticTableDescriptor,
    SemanticViewDescriptor,
    ServiceErrorDetail,
)


class SemduckServiceError(Exception):
    def __init__(self, detail: ServiceErrorDetail):
        super().__init__(detail.message)
        self.detail = detail


def _normalize_error(exc: SemanticViewError) -> SemduckServiceError:
    name = type(exc).__name__.removesuffix("Error").replace("Semantic", "", 1)
    code_chars: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index > 0:
            code_chars.append("_")
        code_chars.append(char.lower())
    code = "".join(code_chars) or "semantic_view"
    return SemduckServiceError(ServiceErrorDetail(code=code, message=str(exc)))


def _infer_definition_format(path: str, explicit_format: str) -> str:
    if explicit_format != "auto":
        return explicit_format

    suffix = Path(path).suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix in {".sql", ".ddl"}:
        return "ddl"

    text = Path(path).read_text(encoding="utf-8")
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first_line.lower().startswith("create semantic view"):
        return "ddl"
    return "yaml"


def _load_definition(conn: Any, args: CheckDefinitionArgs | LoadDefinitionArgs, *, validate_only: bool) -> tuple[LoadResult, str]:
    inferred_format = _infer_definition_format(args.file, args.format)
    loader = load_semantic_ddl_file if inferred_format == "ddl" else load_semantic_yaml_file
    if validate_only:
        result = loader(conn, args.file, validate_only=True)
    else:
        replace_existing = args.replace_existing if isinstance(args, LoadDefinitionArgs) else True
        result = loader(conn, args.file, replace_existing=replace_existing)
    return result, inferred_format


def _describe_object(obj: SemanticObject) -> SemanticObjectDescriptor:
    return SemanticObjectDescriptor(
        name=obj.name,
        object_type=obj.object_type,
        expr=obj.expr,
        data_type=obj.data_type,
        default_agg=obj.default_agg,
        metric_type=obj.metric_type,
    )


def _describe_table(table: SemanticTable) -> SemanticTableDescriptor:
    descriptors = [
        _describe_object(table.dimensions[name])
        for name in sorted(table.dimensions)
    ]
    return SemanticTableDescriptor(
        name=table.name,
        physical_schema=table.physical_schema,
        physical_table=table.physical_table,
        alias=table.alias,
        dimensions=descriptors,
        metrics=[_describe_object(table.metrics[name]) for name in sorted(table.metrics)],
        facts=[_describe_object(table.facts[name]) for name in sorted(table.facts)],
    )


def _describe_registry(registry: SemanticViewRegistry) -> SemanticViewDescriptor:
    return SemanticViewDescriptor(
        view_name=registry.view_name,
        tables=[_describe_table(registry.tables[name]) for name in sorted(registry.tables)],
        joins=[
            SemanticJoinDescriptor(
                left_table=join.left_table,
                right_table=join.right_table,
                join_type=join.join_type,
                join_expr=join.join_expr,
            )
            for join in registry.joins
        ],
    )


def _compile(conn: Any, args: CompileRequestArgs | QueryRequestArgs) -> CompiledSemanticQuery:
    return compile_request(conn, args.request)


def init_registry_service(conn: Any, args: InitRegistryArgs | None = None) -> InitRegistryResult:
    _ = args or InitRegistryArgs()
    init_registry(conn)
    return InitRegistryResult()


def check_definition_service(conn: Any, args: CheckDefinitionArgs) -> CheckDefinitionResult:
    try:
        result, inferred_format = _load_definition(conn, args, validate_only=True)
        return CheckDefinitionResult(
            ok=result.ok,
            view_name=result.view_name,
            validated_only=result.validated_only,
            format=inferred_format,
        )
    except SemanticViewError as exc:
        raise _normalize_error(exc) from exc


def load_definition_service(conn: Any, args: LoadDefinitionArgs) -> LoadDefinitionResult:
    try:
        result, inferred_format = _load_definition(conn, args, validate_only=False)
        return LoadDefinitionResult(
            ok=result.ok,
            view_name=result.view_name,
            validated_only=result.validated_only,
            format=inferred_format,
        )
    except SemanticViewError as exc:
        raise _normalize_error(exc) from exc


def compile_request_service(conn: Any, args: CompileRequestArgs) -> CompileRequestResult:
    try:
        compiled = _compile(conn, args)
        return CompileRequestResult(
            request=compiled.request,
            semantic_view_ref=compiled.parsed_request.semantic_view_ref,
            sql=compiled.sql,
        )
    except SemanticViewError as exc:
        raise _normalize_error(exc) from exc


def query_request_service(conn: Any, args: QueryRequestArgs) -> QueryRequestResult:
    try:
        compiled = _compile(conn, args)
        relation = conn.sql(compiled.sql)
        columns = [column[0] for column in relation.description]
        rows = [list(row) for row in relation.fetchall()]
        return QueryRequestResult(
            request=compiled.request,
            semantic_view_ref=compiled.parsed_request.semantic_view_ref,
            sql=compiled.sql,
            columns=columns,
            rows=rows,
        )
    except SemanticViewError as exc:
        raise _normalize_error(exc) from exc
    except duckdb.Error as exc:
        detail = ServiceErrorDetail(code="runtime", message=str(exc))
        raise SemduckServiceError(detail) from exc


def list_semantic_views_service(conn: Any, args: ListSemanticViewsArgs | None = None) -> ListSemanticViewsResult:
    _ = args or ListSemanticViewsArgs()
    try:
        return ListSemanticViewsResult(view_names=list_semantic_views(conn))
    except duckdb.Error as exc:
        error_message = str(exc).lower()
        if (
            'schema "semantic" does not exist' in error_message
            or "table with name semantic_views does not exist" in error_message
        ):
            return ListSemanticViewsResult(view_names=[])
        raise


def describe_semantic_view_service(conn: Any, args: DescribeSemanticViewArgs) -> SemanticViewDescriptor:
    try:
        registry = get_semantic_view(conn, args.view_name)
        return _describe_registry(registry)
    except SemanticViewError as exc:
        raise _normalize_error(exc) from exc
