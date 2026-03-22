from __future__ import annotations

from pathlib import Path
from typing import Any

from duckdb_semantic.authoring.yaml_loader import load_yaml_spec
from duckdb_semantic.parser.request_parser import parse_request as parse_semantic_request
from duckdb_semantic.registry.reader import load_semantic_view_registry
from duckdb_semantic.registry.schema import init_registry_schema
from duckdb_semantic.registry.writer import write_semantic_view
from duckdb_semantic.runtime.executor import compile_semantic_request, execute_semantic_request
from duckdb_semantic.types import CompiledSemanticQuery, LoadResult, ParsedSemanticRequest, SemanticViewRegistry


def init_registry(conn: Any) -> None:
    init_registry_schema(conn)


def load_semantic_yaml(
    conn: Any,
    yaml_text: str,
    *,
    replace_existing: bool = True,
    validate_only: bool = False,
) -> LoadResult:
    spec = load_yaml_spec(yaml_text)
    return write_semantic_view(
        conn,
        spec,
        source_yaml=yaml_text,
        replace_existing=replace_existing,
        validate_only=validate_only,
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

