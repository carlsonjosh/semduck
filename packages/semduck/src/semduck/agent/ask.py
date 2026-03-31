from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator
from pydantic_ai import Agent, RunContext, capture_run_messages
from pydantic_ai.messages import ModelMessage

from semduck.agent.models import CompileRequestArgs, DescribeSemanticViewArgs, QueryRequestArgs
from semduck.agent.services import (
    SemduckServiceError,
    compile_request_service,
    describe_semantic_view_service,
    list_semantic_views_service,
    query_request_service,
)
from semduck.errors import SemanticParseError, SemanticUnsupportedError
from semduck.llm import create_provider_registry, load_and_resolve_llm_config, resolve_llm_log_dir
from semduck.parser.request_parser import parse_request


class AskPlan(BaseModel):
    answer_text: str
    chosen_view: str
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    where_clause: str | None = None

    @field_validator("chosen_view")
    @classmethod
    def validate_chosen_view(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("chosen_view must not be empty")
        return value

    @field_validator("dimensions", "metrics", mode="before")
    @classmethod
    def normalize_items(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("dimensions and metrics must be lists of strings")

    @field_validator("where_clause")
    @classmethod
    def normalize_where_clause(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if value.lower() in NULLISH_WHERE_CLAUSES:
            return None
        return value or None

    @model_validator(mode="after")
    def validate_request_shape(self) -> "AskPlan":
        if not self.dimensions and not self.metrics:
            raise ValueError("at least one dimension or metric is required")
        _validate_semantic_request(_render_semantic_request(self))
        return self


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
    row_limit: int | None = None
    total_row_count: int = 0
    omitted_row_count: int = 0


class AskExecutionError(Exception):
    def __init__(self, code: str, message: str, troubleshooting: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.troubleshooting = troubleshooting or []


@dataclass
class AskDependencies:
    conn: Any
    requested_view: str | None = None
    sql_only: bool = False


@dataclass
class AskAttemptTrace:
    prompt: str
    output: AskPlan
    messages: list[dict[str, Any]]
    is_retry: bool = False


TEXT_RESULT_ROW_LIMIT = 20
SQL_PREFIXES = ("select", "with", "insert", "update", "delete")
MODEL_MESSAGE_ADAPTER = TypeAdapter(ModelMessage)
NULLISH_WHERE_CLAUSES = {"none", "null", "nil", "n/a", "na"}


def _resolve_agent_model(
    *,
    config: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    llm_log_dir: str | None = None,
    disable_llm_log: bool = False,
) -> tuple[str, str, Any, Path | None]:
    llm_config, resolved = load_and_resolve_llm_config(
        config,
        provider=provider,
        model=model,
    )
    agent_model = create_provider_registry().build_model(resolved)
    log_dir = resolve_llm_log_dir(
        llm_config,
        log_dir=llm_log_dir,
        disable_log=disable_llm_log,
    )
    return resolved.provider_name, resolved.model, agent_model, log_dir


def _troubleshooting_for_error(code: str) -> list[str]:
    hints = {
        "unsupported": [
            "Remove unsupported clauses like ORDER BY, LIMIT, or HAVING from the semantic request.",
            "Use only the semduck request sections: dimensions, metrics, and optional where.",
        ],
        "registry": [
            "Initialize and load semantic views into the DuckDB registry before using ask.",
            "Use list_semantic_views or semduck mcp resources to confirm which views are available.",
        ],
        "parse": [
            "Have the agent regenerate a semduck request instead of raw SQL.",
            "Avoid unsupported clauses like ORDER BY, LIMIT, and HAVING in semantic requests.",
            "Validate the generated request with compile_request before executing it.",
        ],
        "resolution": [
            "Confirm the requested dimensions and metrics exist in describe_semantic_view output.",
            "If the question is ambiguous, constrain the run with --view.",
        ],
        "compile": [
            "Inspect the generated semduck request and re-run compile_request.",
            "Confirm the selected semantic view contains the requested fields.",
        ],
        "validation": [
            "Check the config path and provider settings for typos.",
            "Confirm the selected provider has a model configured.",
        ],
    }
    return hints.get(
        code,
        [
            "Check the configured provider, model, and semantic view inputs.",
            "Use --sql-only to inspect the generated semantic request and compiled SQL separately.",
        ],
    )


def _looks_like_sql(value: str) -> bool:
    candidate = value.strip().lower()
    return candidate.startswith(SQL_PREFIXES)


def _validate_semantic_request(value: str) -> None:
    if _looks_like_sql(value):
        raise ValueError("semantic_request must be a semduck request, not raw SQL")
    try:
        parse_request(value)
    except (SemanticParseError, SemanticUnsupportedError) as exc:
        raise ValueError(str(exc)) from exc


def _render_semantic_request(plan: AskPlan) -> str:
    parts = [plan.chosen_view]
    if plan.dimensions:
        parts.append(f"dimensions {', '.join(plan.dimensions)}")
    if plan.metrics:
        parts.append(f"metrics {', '.join(plan.metrics)}")
    if plan.where_clause:
        parts.append(f"where {plan.where_clause}")
    return " ".join(parts)


def _run_agent_sync(
    agent: Agent[AskDependencies, AskPlan],
    prompt: str,
    deps: AskDependencies,
) -> AskAttemptTrace:
    with capture_run_messages() as messages:
        result = asyncio.run(agent.run(prompt, deps=deps))
    return AskAttemptTrace(
        prompt=prompt,
        output=result.output,
        messages=[MODEL_MESSAGE_ADAPTER.dump_python(message, mode="json") for message in messages],
    )


def _validate_compilable_request(conn: Any, request: str) -> None:
    compile_request_service(conn, CompileRequestArgs(request=request))


def _ask_with_semantic_retry(
    agent: Agent[AskDependencies, AskPlan],
    question: str,
    deps: AskDependencies,
) -> tuple[AskPlan, list[AskAttemptTrace]]:
    initial_attempt = _run_agent_sync(agent, question, deps)
    plan = initial_attempt.output
    try:
        rendered_request = _render_semantic_request(plan)
        _validate_semantic_request(rendered_request)
        _validate_compilable_request(deps.conn, rendered_request)
        return plan, [initial_attempt]
    except (ValueError, SemduckServiceError):
        pass

    retry_prompt = (
        f"{question}\n\n"
        "Your previous structured request was invalid. "
        f"chosen_view={plan.chosen_view!r}, dimensions={plan.dimensions!r}, "
        f"metrics={plan.metrics!r}, where_clause={plan.where_clause!r}\n\n"
        "Retry. Return structured fields, not a free-form semantic_request string. "
        "Set chosen_view to the semantic view name. "
        "Put requested dimensions in dimensions, requested metrics in metrics, and any predicate in where_clause. "
        "Do not include SQL. Do not include ORDER BY, LIMIT, or HAVING. "
        "The rendered request shape is: "
        "<view_name> dimensions <dimension list> metrics <metric list> where <optional predicate>. "
        "Use semduck tools to inspect views and validate the request before finalizing."
    )
    retry_attempt = _run_agent_sync(agent, retry_prompt, deps)
    retry_attempt.is_retry = True
    retry_plan = retry_attempt.output
    try:
        retry_request = _render_semantic_request(retry_plan)
        _validate_semantic_request(retry_request)
        _validate_compilable_request(deps.conn, retry_request)
    except ValueError as exc:
        message = str(exc)
        code = "unsupported" if "Unsupported clause" in message else "parse"
        raise AskExecutionError(
            code=code,
            message=message,
            troubleshooting=_troubleshooting_for_error(code),
        ) from exc
    except SemduckServiceError as exc:
        raise AskExecutionError(
            code=exc.detail.code,
            message=exc.detail.message,
            troubleshooting=_troubleshooting_for_error(exc.detail.code),
        ) from exc
    return retry_plan, [initial_attempt, retry_attempt]


def _build_llm_trace_path(log_dir: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return log_dir / f"ask-{timestamp}-{uuid4().hex}.jsonl"


def _write_llm_trace(
    *,
    log_dir: Path | None,
    provider: str,
    model: str,
    question: str,
    view: str | None,
    execute: bool,
    row_limit: int | None,
    attempts: list[AskAttemptTrace],
    result: AskResult | None = None,
    failure: AskExecutionError | None = None,
) -> None:
    if log_dir is None:
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    trace_path = _build_llm_trace_path(log_dir)
    base_record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "provider": provider,
        "model": model,
        "question": question,
        "requested_view": view,
        "execute": execute,
        "row_limit": row_limit,
    }

    with trace_path.open("a", encoding="utf-8") as handle:
        for index, attempt in enumerate(attempts, start=1):
            record = {
                **base_record,
                "event": "llm_attempt",
                "attempt": index,
                "is_retry": attempt.is_retry,
                "prompt": attempt.prompt,
                "messages": attempt.messages,
                "plan": attempt.output.model_dump(),
            }
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

        if result is not None:
            handle.write(
                json.dumps(
                    {
                        **base_record,
                        "event": "ask_result",
                        "result": result.model_dump(),
                    },
                    ensure_ascii=True,
                )
                + "\n"
            )
        if failure is not None:
            handle.write(
                json.dumps(
                    {
                        **base_record,
                        "event": "ask_error",
                        "error": {
                            "code": failure.code,
                            "message": failure.message,
                            "troubleshooting": failure.troubleshooting,
                        },
                    },
                    ensure_ascii=True,
                )
                + "\n"
            )


def create_ask_agent(model: Any) -> Agent[AskDependencies, AskPlan]:
    agent = Agent(
        model,
        deps_type=AskDependencies,
        output_type=AskPlan,
        system_prompt=(
            "You translate analytics questions into semduck semantic requests. "
            "Do not invent arbitrary SQL as the primary answer. "
            "Use the available semduck tools to inspect semantic views before choosing a request. "
            "Verify dimensions and metrics against describe_semantic_view before finalizing a request. "
            "If you use compile or query tools, use them only with semduck requests. "
            "Return structured output fields: chosen_view, dimensions, metrics, where_clause, and answer_text. "
            "Do not put a whole semantic request or SQL string into one field. "
            "The semantic request grammar is: <view_name> dimensions <dimension list> metrics <metric list> "
            "where <optional predicate>. Only dimensions, metrics, and optional where are supported. "
            "Never include SQL clauses like ORDER BY, LIMIT, GROUP BY, HAVING, or raw SELECT statements. "
            "Dimensions and metrics should be arrays of request items like ['customer_name'] or ['total_revenue']. "
            "where_clause should contain only the predicate body, for example region = 'US'. "
            "If no predicate is needed, return where_clause as null, not the string 'None' or 'null'."
        ),
    )

    @agent.system_prompt
    def runtime_instructions(ctx: RunContext[AskDependencies]) -> str:
        if ctx.deps.requested_view:
            return (
                f"The user requested semantic view `{ctx.deps.requested_view}`. "
                "You must use that view unless compilation proves it invalid."
            )
        return (
            "If multiple semantic views exist, inspect them and choose the most relevant one. "
            "If no semantic views are available, do not fabricate a request; explain that the registry needs to be loaded."
        )

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
    row_limit: int | None = None,
    llm_log_dir: str | None = None,
    disable_llm_log: bool = False,
) -> AskResult:
    attempts: list[AskAttemptTrace] = []
    resolved_log_dir: Path | None = None
    try:
        resolved_model = _resolve_agent_model(
            config=config,
            provider=provider,
            model=model,
            llm_log_dir=llm_log_dir,
            disable_llm_log=disable_llm_log,
        )
        if len(resolved_model) == 3:
            provider_name, model_name, agent_model = resolved_model
        else:
            provider_name, model_name, agent_model, resolved_log_dir = resolved_model
        agent = create_ask_agent(agent_model)
        conn, should_close = _connect_if_needed(conn_or_db)
    except (ValueError, FileNotFoundError) as exc:
        raise AskExecutionError(
            code="configuration",
            message=str(exc),
            troubleshooting=[
                "Check the config file path and provider name.",
                "Confirm the selected provider has a configured model and reachable base URL.",
            ],
        ) from exc

    try:
        try:
            deps = AskDependencies(
                conn=conn,
                requested_view=view,
                sql_only=not execute,
            )
            plan, attempts = _ask_with_semantic_retry(agent, question, deps)
            semantic_request = _render_semantic_request(plan)

            compiled = compile_request_service(conn, CompileRequestArgs(request=semantic_request))
            columns: list[str] = []
            rows: list[list[Any]] = []
            total_row_count = 0
            omitted_row_count = 0
            if execute:
                query_result = query_request_service(conn, QueryRequestArgs(request=semantic_request))
                columns = query_result.columns
                total_row_count = len(query_result.rows)
                if row_limit is not None and row_limit >= 0:
                    rows = query_result.rows[:row_limit]
                    omitted_row_count = max(total_row_count - len(rows), 0)
                else:
                    rows = query_result.rows

            result = AskResult(
                answer_text=plan.answer_text,
                semantic_request=semantic_request,
                sql=compiled.sql,
                columns=columns,
                rows=rows,
                executed=execute,
                provider=provider_name,
                model=model_name,
                chosen_view=compiled.semantic_view_ref,
                row_limit=row_limit,
                total_row_count=total_row_count,
                omitted_row_count=omitted_row_count,
            )
            _write_llm_trace(
                log_dir=resolved_log_dir,
                provider=provider_name,
                model=model_name,
                question=question,
                view=view,
                execute=execute,
                row_limit=row_limit,
                attempts=attempts,
                result=result,
            )
            return result
        except AskExecutionError as exc:
            _write_llm_trace(
                log_dir=resolved_log_dir,
                provider=provider_name,
                model=model_name,
                question=question,
                view=view,
                execute=execute,
                row_limit=row_limit,
                attempts=attempts,
                failure=exc,
            )
            raise
        except Exception as exc:
            if hasattr(exc, "detail") and hasattr(exc.detail, "code"):
                code = exc.detail.code
                troubleshooting = _troubleshooting_for_error(code)
            else:
                code = "runtime"
                troubleshooting = _troubleshooting_for_error(code)
            failure = AskExecutionError(
                code=code,
                message=str(exc),
                troubleshooting=troubleshooting,
            )
            _write_llm_trace(
                log_dir=resolved_log_dir,
                provider=provider_name,
                model=model_name,
                question=question,
                view=view,
                execute=execute,
                row_limit=row_limit,
                attempts=attempts,
                failure=failure,
            )
            raise failure from exc
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
            display_rows = result.rows[:TEXT_RESULT_ROW_LIMIT]
            for row in display_rows:
                lines.append(" | ".join("" if value is None else str(value) for value in row))
            explicit_omitted = getattr(result, "omitted_row_count", None)
            if explicit_omitted is None:
                omitted_count = len(result.rows) - len(display_rows)
            else:
                omitted_count = explicit_omitted
            if omitted_count > 0:
                lines.append(f"... {omitted_count} more rows omitted")
        else:
            lines.append("(no rows)")
    else:
        lines.append("Execution: skipped (--sql-only)")
    return "\n".join(lines)


def format_ask_result_json(result: AskResult) -> str:
    return json.dumps(result.model_dump(), indent=2)
