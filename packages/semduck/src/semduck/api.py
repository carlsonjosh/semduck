from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from semduck.authoring.yaml_loader import load_yaml_spec
from semduck.parser.request_parser import parse_request as parse_semantic_request
from semduck.registry.reader import load_semantic_view_registry
from semduck.registry.schema import init_registry_schema
from semduck.registry.writer import write_semantic_view
from semduck.runtime.executor import compile_semantic_request, execute_semantic_request
from semduck.types import CompiledSemanticQuery, LoadResult, ParsedSemanticRequest, SemanticViewRegistry


def init_registry(conn: Any) -> None:
    init_registry_schema(conn)


def load_semantic_spec(
    conn: Any,
    spec: dict[str, Any],
    *,
    replace_existing: bool = True,
    validate_only: bool = False,
    source_yaml: str | None = None,
) -> LoadResult:
    source = source_yaml or json.dumps(spec, sort_keys=True)
    return write_semantic_view(
        conn,
        spec,
        source_yaml=source,
        replace_existing=replace_existing,
        validate_only=validate_only,
    )


def check_semantic_spec(conn: Any, spec: dict[str, Any]) -> LoadResult:
    return load_semantic_spec(conn, spec, validate_only=True)


def load_semantic_yaml(
    conn: Any,
    yaml_text: str,
    *,
    replace_existing: bool = True,
    validate_only: bool = False,
) -> LoadResult:
    spec = load_yaml_spec(yaml_text)
    return load_semantic_spec(
        conn,
        spec,
        replace_existing=replace_existing,
        validate_only=validate_only,
        source_yaml=yaml_text,
    )


def load_semantic_yaml_file(
    conn: Any,
    path: str,
    *,
    replace_existing: bool = True,
    validate_only: bool = False,
) -> LoadResult:
    yaml_text = Path(path).read_text(encoding="utf-8")
    return load_semantic_yaml(
        conn,
        yaml_text,
        replace_existing=replace_existing,
        validate_only=validate_only,
    )


def parse_request(request: str) -> ParsedSemanticRequest:
    return parse_semantic_request(request)


def get_semantic_view(conn: Any, view_name: str) -> SemanticViewRegistry:
    return load_semantic_view_registry(conn, view_name)


def compile_request(conn: Any, request: str) -> CompiledSemanticQuery:
    return compile_semantic_request(conn, request)


def execute_request(conn: Any, request: str):
    return execute_semantic_request(conn, request)


def compile_request_sql(conn: Any, request: str) -> str:
    return compile_request(conn, request).sql


def register_connection(conn: Any) -> None:
    from semduck.dbt.plugin import register_plugin_functions

    init_registry(conn)
    register_plugin_functions(conn)
