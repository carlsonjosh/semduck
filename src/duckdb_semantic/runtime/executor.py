from __future__ import annotations

from typing import Any

from duckdb_semantic.compiler.sql_compiler import compile_sql
from duckdb_semantic.parser.request_parser import parse_request
from duckdb_semantic.planner.resolver import build_query_plan
from duckdb_semantic.registry.reader import load_semantic_view_registry
from duckdb_semantic.types import CompiledSemanticQuery


def compile_semantic_request(conn: Any, request: str) -> CompiledSemanticQuery:
    parsed = parse_request(request)
    registry = load_semantic_view_registry(conn, parsed.semantic_view_ref)
    plan = build_query_plan(parsed, registry)
    sql = compile_sql(plan, registry)
    return CompiledSemanticQuery(
        request=request,
        parsed_request=parsed,
        plan=plan,
        sql=sql,
    )


def execute_semantic_request(conn: Any, request: str):
    compiled = compile_semantic_request(conn, request)
    return conn.sql(compiled.sql)

