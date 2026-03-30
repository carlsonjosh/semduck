from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from semduck.agent.models import CompileRequestArgs, DescribeSemanticViewArgs, QueryRequestArgs
from semduck.agent.services import (
    compile_request_service,
    describe_semantic_view_service,
    list_semantic_views_service,
    query_request_service,
)
from semduck.llm import create_provider_registry, load_and_resolve_llm_config


class AskPlan(BaseModel):
    answer_text: str
    semantic_request: str
    chosen_view: str


class AskResult(BaseModel):
    answer_text: str
    semantic_request: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    executed: bool
    provider: str
    model: str
    chosen_view: str


@dataclass
class AskDependencies:
    conn: Any
    requested_view: str | None = None
    sql_only: bool = False


def _resolve_agent_model(
    *,
    config: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[str, str, Any]:
    _, resolved = load_and_resolve_llm_config(
        config,
        provider=provider,
        model=model,
    )
    agent_model = create_provider_registry().build_model(resolved)
    return resolved.provider_name, resolved.model, agent_model


def create_ask_agent(model: Any) -> Agent[AskDependencies, AskPlan]:
    agent = Agent(
        model,
        deps_type=AskDependencies,
        output_type=AskPlan,
        system_prompt=(
            "You translate analytics questions into semduck semantic requests. "
            "Do not invent arbitrary SQL as the primary answer. "
            "Use the available semduck tools to inspect semantic views before choosing a request. "
            "If you use compile or query tools, use them only with semduck requests. "
            "Your final output must contain a concise answer_text, one semantic_request, and the chosen_view."
        ),
    )

    @agent.system_prompt
    def runtime_instructions(ctx: RunContext[AskDependencies]) -> str:
        if ctx.deps.requested_view:
            return (
                f"The user requested semantic view `{ctx.deps.requested_view}`. "
                "You must use that view unless compilation proves it invalid."
            )
        return "If multiple semantic views exist, inspect them and choose the most relevant one."

    @agent.system_prompt
    def sql_only_instructions(ctx: RunContext[AskDependencies]) -> str:
        if ctx.deps.sql_only:
            return (
                "This run is SQL-only. Do not execute queries for the final answer. "
                "You may inspect views and validate a semantic request, but final output should assume no query execution."
            )
        return "Query execution is allowed if it helps you answer accurately."

    @agent.tool
    def list_semantic_views(ctx: RunContext[AskDependencies]) -> list[str]:
        """List the semantic views available in the connected semduck registry."""
        return list_semantic_views_service(ctx.deps.conn).view_names

    @agent.tool
    def describe_semantic_view(ctx: RunContext[AskDependencies], view_name: str) -> dict[str, Any]:
        """Describe one semantic view, including its tables, dimensions, facts, metrics, and joins."""
        return describe_semantic_view_service(
            ctx.deps.conn,
            DescribeSemanticViewArgs(view_name=view_name),
        ).model_dump()

    @agent.tool
    def compile_semantic_request(ctx: RunContext[AskDependencies], request: str) -> dict[str, Any]:
        """Compile a semduck semantic request to SQL without executing it."""
        return compile_request_service(
            ctx.deps.conn,
            CompileRequestArgs(request=request),
        ).model_dump()

    @agent.tool
    def query_semantic_request(ctx: RunContext[AskDependencies], request: str) -> dict[str, Any]:
        """Execute a semduck semantic request and return SQL plus tabular results."""
        if ctx.deps.sql_only:
            raise ValueError("query_semantic_request is unavailable during sql-only runs")
        return query_request_service(
            ctx.deps.conn,
            QueryRequestArgs(request=request),
        ).model_dump()

    return agent


def _connect_if_needed(conn_or_db: Any) -> tuple[Any, bool]:
    if hasattr(conn_or_db, "sql") and hasattr(conn_or_db, "execute"):
        return conn_or_db, False
    path = str(conn_or_db)
    return duckdb.connect(path), True


def ask_question(
    conn_or_db: Any,
    question: str,
    *,
    config: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    view: str | None = None,
    execute: bool = True,
) -> AskResult:
    provider_name, model_name, agent_model = _resolve_agent_model(
        config=config,
        provider=provider,
        model=model,
    )
    agent = create_ask_agent(agent_model)
    conn, should_close = _connect_if_needed(conn_or_db)
    try:
        plan = agent.run_sync(
            question,
            deps=AskDependencies(
                conn=conn,
                requested_view=view,
                sql_only=not execute,
            ),
        ).output

        compiled = compile_request_service(conn, CompileRequestArgs(request=plan.semantic_request))
        columns: list[str] = []
        rows: list[list[Any]] = []
        if execute:
            query_result = query_request_service(conn, QueryRequestArgs(request=plan.semantic_request))
            columns = query_result.columns
            rows = query_result.rows

        return AskResult(
            answer_text=plan.answer_text,
            semantic_request=plan.semantic_request,
            sql=compiled.sql,
            columns=columns,
            rows=rows,
            executed=execute,
            provider=provider_name,
            model=model_name,
            chosen_view=compiled.semantic_view_ref,
        )
    finally:
        if should_close:
            conn.close()


def format_ask_result_text(result: AskResult) -> str:
    lines = [
        f"Answer: {result.answer_text}",
        f"View: {result.chosen_view}",
        f"Provider: {result.provider}",
        f"Model: {result.model}",
        f"Request: {result.semantic_request}",
        "SQL:",
        result.sql,
    ]
    if result.executed:
        lines.append("Results:")
        if result.columns:
            lines.append(" | ".join(result.columns))
            for row in result.rows:
                lines.append(" | ".join("" if value is None else str(value) for value in row))
        else:
            lines.append("(no rows)")
    else:
        lines.append("Execution: skipped (--sql-only)")
    return "\n".join(lines)


def format_ask_result_json(result: AskResult) -> str:
    return json.dumps(result.model_dump(), indent=2)
