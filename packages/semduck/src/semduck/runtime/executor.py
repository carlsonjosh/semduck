from __future__ import annotations

from typing import Any

from semduck.compiler.sql_compiler import compile_sql
from semduck.parser.request_parser import parse_request
from semduck.planner.resolver import build_query_plan
from semduck.registry.reader import load_semantic_view_registry
from semduck.types import CompiledSemanticQuery, ParsedSemanticRequest


def compile_parsed_semantic_request(
    conn: Any,
    parsed: ParsedSemanticRequest,
    *,
    request: str | None = None,
) -> CompiledSemanticQuery:
    registry = load_semantic_view_registry(conn, parsed.semantic_view_ref)
    plan = build_query_plan(parsed, registry)
    sql = compile_sql(plan, registry)
    return CompiledSemanticQuery(
        request=request or parsed.semantic_view_ref,
        parsed_request=parsed,
        plan=plan,
        sql=sql,
    )


def compile_semantic_request(conn: Any, request: str) -> CompiledSemanticQuery:
    parsed = parse_request(request)
    return compile_parsed_semantic_request(conn, parsed, request=request)


def execute_semantic_request(conn: Any, request: str):
    compiled = compile_semantic_request(conn, request)
    return conn.sql(compiled.sql)
