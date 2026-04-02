from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
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
from semduck.llm import (
    create_provider_registry,
    load_llm_config,
    resolve_llm_log_dir,
    resolve_llm_task_configs,
)
from semduck.llm.config import ResolvedLLMConfig
from semduck.parser.request_parser import parse_request


ASK_PLAN_TASK = "ask_plan"
ASK_SUMMARY_TASK = "ask_summary"
TEXT_RESULT_ROW_LIMIT = 20
SQL_PREFIXES = ("select", "with", "insert", "update", "delete")
MODEL_MESSAGE_ADAPTER = TypeAdapter(ModelMessage)
NULLISH_WHERE_CLAUSES = {"none", "null", "nil", "n/a", "na"}
AskProgressReporter = Callable[[str], None]


def _normalize_nullish_token(value: str) -> str:
    token = value.strip()
    changed = True
    while changed and token:
        changed = False
        if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
            token = token[1:-1].strip()
            changed = True
        if len(token) >= 2 and token[0] == "[" and token[-1] == "]":
            inner = token[1:-1].strip()
            if "," not in inner:
                token = inner
                changed = True
    return token


class AskPlan(BaseModel):
    chosen_view: str | None
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    where_clause: str | None = None

    @field_validator("chosen_view")
    @classmethod
    def validate_chosen_view(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _normalize_nullish_token(value)
        if value.lower() in NULLISH_WHERE_CLAUSES:
            return None
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
        value = _normalize_nullish_token(value)
        if value.lower() in NULLISH_WHERE_CLAUSES:
            return None
        return value or None

    @model_validator(mode="after")
    def validate_request_shape(self) -> "AskPlan":
        if self.chosen_view is None:
            if self.dimensions or self.metrics:
                raise ValueError("dimensions and metrics must be empty when chosen_view is null")
            if self.where_clause is not None:
                raise ValueError("where_clause must be null when chosen_view is null")
            return self
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
    summary_provider: str | None = None
    summary_model: str | None = None
    chosen_view: str
    row_limit: int | None = None
    total_row_count: int = 0
    omitted_row_count: int = 0


class AskExecutionError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        troubleshooting: list[str] | None = None,
        *,
        failure_stage: str | None = None,
        attempts: list["AskAttemptTrace"] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.troubleshooting = troubleshooting or []
        self.failure_stage = failure_stage
        self.attempts = attempts or []


@dataclass
class AskDependencies:
    conn: Any
    requested_view: str | None = None


@dataclass
class AskStageModel:
    stage: str
    provider_name: str
    model_name: str
    agent_model: Any


@dataclass
class AskAttemptTrace:
    stage: str
    prompt: str
    provider: str
    model: str
    output: dict[str, Any]
    messages: list[dict[str, Any]]
    started_at: str
    finished_at: str
    duration_ms: int
    is_retry: bool = False


class AskAgentRunError(Exception):
    def __init__(self, attempt: AskAttemptTrace, cause: Exception):
        super().__init__(str(cause))
        self.attempt = attempt
        self.cause = cause


def _serialize_output(output: Any) -> dict[str, Any]:
    if hasattr(output, "model_dump"):
        return output.model_dump()
    return {"value": output}


def _emit_progress(progress: AskProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _resolve_ask_models(
    *,
    config: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    llm_log_dir: str | None = None,
    disable_llm_log: bool = False,
) -> tuple[AskStageModel, AskStageModel, Path | None]:
    llm_config = load_llm_config(config)
    resolved_tasks = resolve_llm_task_configs(
        llm_config,
        task_names=(ASK_PLAN_TASK, ASK_SUMMARY_TASK),
        provider=provider,
        model=model,
    )
    registry = create_provider_registry()
    plan_config = resolved_tasks[ASK_PLAN_TASK]
    summary_config = resolved_tasks[ASK_SUMMARY_TASK]
    log_dir = resolve_llm_log_dir(
        llm_config,
        log_dir=llm_log_dir,
        disable_log=disable_llm_log,
    )
    return (
        AskStageModel(
            stage=ASK_PLAN_TASK,
            provider_name=plan_config.provider_name,
            model_name=plan_config.model,
            agent_model=registry.build_model(plan_config),
        ),
        AskStageModel(
            stage=ASK_SUMMARY_TASK,
            provider_name=summary_config.provider_name,
            model_name=summary_config.model,
            agent_model=registry.build_model(summary_config),
        ),
        log_dir,
    )


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
    if plan.chosen_view is None:
        raise ValueError("cannot render semantic_request when chosen_view is null")
    parts = [plan.chosen_view]
    if plan.dimensions:
        parts.append(f"dimensions {', '.join(plan.dimensions)}")
    if plan.metrics:
        parts.append(f"metrics {', '.join(plan.metrics)}")
    if plan.where_clause:
        parts.append(f"where {plan.where_clause}")
    return " ".join(parts)


def _run_agent_sync(
    agent: Agent[Any, Any],
    prompt: str,
    *,
    deps: Any,
    stage_model: AskStageModel,
) -> tuple[Any, AskAttemptTrace]:
    started_at = datetime.now(UTC).isoformat()
    started_perf = perf_counter()
    with capture_run_messages() as messages:
        try:
            result = asyncio.run(agent.run(prompt, deps=deps))
        except Exception as exc:
            finished_at = datetime.now(UTC).isoformat()
            duration_ms = int((perf_counter() - started_perf) * 1000)
            raise AskAgentRunError(
                AskAttemptTrace(
                    stage=stage_model.stage,
                    prompt=prompt,
                    provider=stage_model.provider_name,
                    model=stage_model.model_name,
                    output={
                        "error": {
                            "type": type(exc).__name__,
                            "message": str(exc),
                        }
                    },
                    messages=[MODEL_MESSAGE_ADAPTER.dump_python(message, mode="json") for message in messages],
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                ),
                exc,
            ) from exc
    output = result.output
    finished_at = datetime.now(UTC).isoformat()
    duration_ms = int((perf_counter() - started_perf) * 1000)
    return output, AskAttemptTrace(
        stage=stage_model.stage,
        prompt=prompt,
        provider=stage_model.provider_name,
        model=stage_model.model_name,
        output=_serialize_output(output),
        messages=[MODEL_MESSAGE_ADAPTER.dump_python(message, mode="json") for message in messages],
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
    )


def _validate_compilable_request(conn: Any, request: str) -> None:
    compile_request_service(conn, CompileRequestArgs(request=request))


def _is_empty_plan(plan: AskPlan) -> bool:
    return (
        plan.chosen_view is None
        and not plan.dimensions
        and not plan.metrics
        and plan.where_clause is None
    )


def _ask_with_semantic_retry(
    agent: Agent[AskDependencies, AskPlan],
    stage_model: AskStageModel,
    question: str,
    deps: AskDependencies,
    *,
    progress: AskProgressReporter | None = None,
) -> tuple[AskPlan, list[AskAttemptTrace]]:
    attempts: list[AskAttemptTrace] = []
    _emit_progress(progress, "planning semantic request")
    try:
        plan, initial_attempt = _run_agent_sync(agent, question, deps=deps, stage_model=stage_model)
    except AskAgentRunError as exc:
        attempts.append(exc.attempt)
        raise AskExecutionError(
            code="runtime",
            message=str(exc.cause),
            troubleshooting=_troubleshooting_for_error("runtime"),
            failure_stage=stage_model.stage,
            attempts=attempts,
        ) from exc.cause
    attempts.append(initial_attempt)
    if _is_empty_plan(plan):
        return plan, attempts
    try:
        rendered_request = _render_semantic_request(plan)
        _validate_semantic_request(rendered_request)
        _validate_compilable_request(deps.conn, rendered_request)
        return plan, attempts
    except (ValueError, SemduckServiceError):
        pass

    _emit_progress(progress, "retrying planner after invalid request")
    retry_prompt = (
        f"{question}\n\n"
        "Your previous structured request was invalid. "
        f"chosen_view={plan.chosen_view!r}, dimensions={plan.dimensions!r}, "
        f"metrics={plan.metrics!r}, where_clause={plan.where_clause!r}\n\n"
        "Your previous response did not match the required output format."
        ""
        "Return only the required structured fields:"
        "- chosen_view"
        "- dimensions"
        "- metrics"
        "- where_clause"
        ""
        "Rules:"
        "- Do not explain."
        "- Do not output prose."
        "- Do not output pseudo-tool syntax."
        "- Do not output code fences."
        "- Do not describe the tools."
        "- If no predicate is needed, where_clause must be null."
        "- If no valid view can be confirmed, return:"
        "  chosen_view = null"
        "  dimensions = []"
        "  metrics = []"
        "  where_clause = null"
    )
    try:
        retry_plan, retry_attempt = _run_agent_sync(agent, retry_prompt, deps=deps, stage_model=stage_model)
    except AskAgentRunError as exc:
        exc.attempt.is_retry = True
        attempts.append(exc.attempt)
        raise AskExecutionError(
            code="runtime",
            message=str(exc.cause),
            troubleshooting=_troubleshooting_for_error("runtime"),
            failure_stage=stage_model.stage,
            attempts=attempts,
        ) from exc.cause
    retry_attempt.is_retry = True
    attempts.append(retry_attempt)
    if _is_empty_plan(retry_plan):
        return retry_plan, attempts
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
            failure_stage=stage_model.stage,
            attempts=attempts,
        ) from exc
    except SemduckServiceError as exc:
        raise AskExecutionError(
            code=exc.detail.code,
            message=exc.detail.message,
            troubleshooting=_troubleshooting_for_error(exc.detail.code),
            failure_stage=stage_model.stage,
            attempts=attempts,
        ) from exc
    return retry_plan, attempts


def _build_summary_prompt(
    *,
    question: str,
    semantic_request: str,
    sql: str,
    columns: list[str],
    rows: list[list[Any]],
    total_row_count: int,
    omitted_row_count: int,
) -> str:
    payload = {
        "question": question,
        "semantic_request": semantic_request,
        "sql": sql,
        "columns": columns,
        "rows": rows,
        "total_row_count": total_row_count,
        "omitted_row_count": omitted_row_count,
    }
    return json.dumps(payload, indent=2, default=str)


def _summarize_results(
    agent: Agent[None, str],
    stage_model: AskStageModel,
    *,
    question: str,
    semantic_request: str,
    sql: str,
    columns: list[str],
    rows: list[list[Any]],
    total_row_count: int,
    omitted_row_count: int,
) -> tuple[str, list[AskAttemptTrace]]:
    prompt = _build_summary_prompt(
        question=question,
        semantic_request=semantic_request,
        sql=sql,
        columns=columns,
        rows=rows,
        total_row_count=total_row_count,
        omitted_row_count=omitted_row_count,
    )
    try:
        summary, attempt = _run_agent_sync(agent, prompt, deps=None, stage_model=stage_model)
    except AskAgentRunError as exc:
        raise AskExecutionError(
            code="runtime",
            message=str(exc.cause),
            troubleshooting=_troubleshooting_for_error("runtime"),
            failure_stage=stage_model.stage,
            attempts=[exc.attempt],
        ) from exc.cause
    summary = str(summary).strip()
    if not summary:
        raise AskExecutionError(
            code="runtime",
            message="Summary model returned an empty answer",
            troubleshooting=_troubleshooting_for_error("runtime"),
            failure_stage=stage_model.stage,
            attempts=[attempt],
        )
    return summary, [attempt]


def _deterministic_sql_only_answer(semantic_request: str) -> str:
    return f"Prepared semantic request without executing it: {semantic_request}"


def _build_llm_trace_path(log_dir: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return log_dir / f"ask-{timestamp}-{uuid4().hex}.jsonl"


def _write_llm_trace(
    *,
    log_dir: Path | None,
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
        "question": question,
        "requested_view": view,
        "execute": execute,
        "row_limit": row_limit,
    }

    with trace_path.open("a", encoding="utf-8") as handle:
        for index, attempt in enumerate(attempts, start=1):
            record = {
                **base_record,
                "event": f"{attempt.stage}_attempt",
                "attempt": index,
                "is_retry": attempt.is_retry,
                "provider": attempt.provider,
                "model": attempt.model,
                "started_at": attempt.started_at,
                "finished_at": attempt.finished_at,
                "duration_ms": attempt.duration_ms,
                "prompt": attempt.prompt,
                "messages": attempt.messages,
                "output": attempt.output,
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
                        "failure_stage": failure.failure_stage,
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


def create_ask_planner(model: Any) -> Agent[AskDependencies, AskPlan]:
    agent = Agent(
        model,
        deps_type=AskDependencies,
        output_type=AskPlan,
        system_prompt=(
            "You translate analytics questions into semduck semantic requests. "
            "Use the available semduck tools to inspect semantic views before choosing a request. "
            "Follow this exact process: "
            "1. Call list_semantic_views. "
            "2. Identify the most relevant semantic view. "
            "3. Call describe_semantic_view for that view. "
            "4. Choose only dimensions and metrics confirmed by describe_semantic_view. "
            "5. Return the final structured result. "
            "Return only these structured output fields: chosen_view, dimensions, metrics, where_clause. "
            "Rules: "
            "Do not return answer text, summaries, SQL, markdown, code fences, pseudo-code, or commentary. "
            "Do not describe tool calls or tool schemas in text. "
            "Do not output strings like function <nil>, list_semantic_views, describe_semantic_view, or final_result unless making an actual tool call through the tool interface. "
            "Do not guess or invent a view name, dimension, metric, join, or filter. "
            "Only use dimensions and metrics confirmed by describe_semantic_view. "
            "Do not add dimensions just because they appear in a join. The semantic view handles joins internally. "
            "If no predicate is needed, where_clause must be null. "
            "Do not return an empty string, 'null', 'None', or an object for where_clause. "
            "If no semantic views are available, return: chosen_view = null, dimensions = [], metrics = [], where_clause = null. "
            "Do not explain in prose."
            ""
            "Examples:"
            "Question: 'What is total revenue by customer name?'"
            "Return:"
            "{"
            "\"chosen_view\": \"orders\","
            "\"dimensions\": [\"customer_name\"],"
            "\"metrics\": [\"total_revenue\"],"
            "\"where_clause\": null"
            "}"
            ""
            "Question: 'What is total revenue by customer name in the US?'"
            "Return:"
            "{"
            "\"chosen_view\": \"orders\","
            "\"dimensions\": [\"customer_name\"],"
            "\"metrics\": [\"total_revenue\"],"
            "\"where_clause\": \"region = 'US'\""
            "}"
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
            "If no semantic views are available, do not fabricate a request."
            "Return the structured fields exactly as:"
            "{\"chosen_view\": null, \"dimensions\": [], \"metrics\": [], \"where_clause\": null}"
            "Do not explain in prose."
        )

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

    return agent


def create_ask_summary_agent(model: Any) -> Agent[None, str]:
    return Agent(
        model,
        output_type=str,
        system_prompt=(
            "You summarize executed semduck query results for analytics questions. "
            "Use only the provided question, semantic request, SQL, columns, and rows. "
            "Prefer one concise sentence. "
            "If there are multiple rows, you may instead return a compact markdown table with the provided columns and rows. "
            "Output only the final answer text. "
            "Do not show your reasoning, analysis, thinking process, draft text, or decision process. "
            "Do not invent rows, aggregations, or facts that are not present in the payload. "
            "If omitted_row_count is 0, do not mention truncation or omitted rows."
            "If omitted_row_count is greater than zero, mention that the answer is based on truncated results. "
            "If there are no rows, say that no matching rows were returned. "
        ),
    )


def create_ask_agent(model: Any) -> Agent[AskDependencies, AskPlan]:
    return create_ask_planner(model)


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
    progress: AskProgressReporter | None = None,
) -> AskResult:
    attempts: list[AskAttemptTrace] = []
    resolved_log_dir: Path | None = None
    try:
        _emit_progress(progress, "resolving ask configuration")
        plan_stage, summary_stage, resolved_log_dir = _resolve_ask_models(
            config=config,
            provider=provider,
            model=model,
            llm_log_dir=llm_log_dir,
            disable_llm_log=disable_llm_log,
        )
        planner = create_ask_planner(plan_stage.agent_model)
        summary_agent = create_ask_summary_agent(summary_stage.agent_model)
        conn, should_close = _connect_if_needed(conn_or_db)
    except (ValueError, FileNotFoundError) as exc:
        _emit_progress(progress, "failed")
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
            )
            plan, plan_attempts = _ask_with_semantic_retry(
                planner,
                plan_stage,
                question,
                deps,
                progress=progress,
            )
            attempts.extend(plan_attempts)
            if _is_empty_plan(plan):
                raise AskExecutionError(
                    code="registry",
                    message="No semantic views are available in the registry.",
                    troubleshooting=_troubleshooting_for_error("registry"),
                    failure_stage=plan_stage.stage,
                )
            semantic_request = _render_semantic_request(plan)

            _emit_progress(progress, "compiling semantic request")
            try:
                compiled = compile_request_service(conn, CompileRequestArgs(request=semantic_request))
            except SemduckServiceError as exc:
                raise AskExecutionError(
                    code=exc.detail.code,
                    message=exc.detail.message,
                    troubleshooting=_troubleshooting_for_error(exc.detail.code),
                    failure_stage="compile",
                ) from exc
            columns: list[str] = []
            rows: list[list[Any]] = []
            total_row_count = 0
            omitted_row_count = 0
            answer_text = _deterministic_sql_only_answer(semantic_request)
            summary_provider: str | None = None
            summary_model: str | None = None

            if execute:
                _emit_progress(progress, "executing semantic request")
                try:
                    query_result = query_request_service(conn, QueryRequestArgs(request=semantic_request))
                except SemduckServiceError as exc:
                    raise AskExecutionError(
                        code=exc.detail.code,
                        message=exc.detail.message,
                        troubleshooting=_troubleshooting_for_error(exc.detail.code),
                        failure_stage="execute",
                    ) from exc
                columns = query_result.columns
                total_row_count = len(query_result.rows)
                if row_limit is not None and row_limit >= 0:
                    rows = query_result.rows[:row_limit]
                    omitted_row_count = max(total_row_count - len(rows), 0)
                else:
                    rows = query_result.rows
                _emit_progress(progress, "summarizing results")
                summary, summary_attempts = _summarize_results(
                    summary_agent,
                    summary_stage,
                    question=question,
                    semantic_request=semantic_request,
                    sql=compiled.sql,
                    columns=columns,
                    rows=rows,
                    total_row_count=total_row_count,
                    omitted_row_count=omitted_row_count,
                )
                attempts.extend(summary_attempts)
                answer_text = summary
                summary_provider = summary_stage.provider_name
                summary_model = summary_stage.model_name
            else:
                _emit_progress(progress, "skipping execution (--sql-only)")

            result = AskResult(
                answer_text=answer_text,
                semantic_request=semantic_request,
                sql=compiled.sql,
                columns=columns,
                rows=rows,
                executed=execute,
                provider=plan_stage.provider_name,
                model=plan_stage.model_name,
                summary_provider=summary_provider,
                summary_model=summary_model,
                chosen_view=compiled.semantic_view_ref,
                row_limit=row_limit,
                total_row_count=total_row_count,
                omitted_row_count=omitted_row_count,
            )
            _write_llm_trace(
                log_dir=resolved_log_dir,
                question=question,
                view=view,
                execute=execute,
                row_limit=row_limit,
                attempts=attempts,
                result=result,
            )
            _emit_progress(progress, "finished")
            return result
        except AskExecutionError as exc:
            _emit_progress(progress, "failed")
            if exc.attempts:
                attempts.extend(exc.attempts)
            _write_llm_trace(
                log_dir=resolved_log_dir,
                question=question,
                view=view,
                execute=execute,
                row_limit=row_limit,
                attempts=attempts,
                failure=exc,
            )
            raise
        except Exception as exc:
            _emit_progress(progress, "failed")
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
                failure_stage="runtime",
            )
            _write_llm_trace(
                log_dir=resolved_log_dir,
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
    ]
    summary_provider = getattr(result, "summary_provider", None)
    summary_model = getattr(result, "summary_model", None)
    if summary_provider and summary_model:
        lines.append(f"Summary Provider: {summary_provider}")
        lines.append(f"Summary Model: {summary_model}")
    lines.extend(
        [
            f"Request: {result.semantic_request}",
            "SQL:",
            result.sql,
        ]
    )
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
