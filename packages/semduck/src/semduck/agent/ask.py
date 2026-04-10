from __future__ import annotations

import asyncio
import csv
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Literal
from uuid import uuid4

import duckdb
from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator
from pydantic_ai import Agent, RunContext, capture_run_messages
from pydantic_ai.messages import ModelMessage

from semduck.agent.models import DescribeSemanticViewArgs
from semduck.agent.services import (
    describe_semantic_view_service,
    list_semantic_views_service,
)
from semduck.agent.validation import DEFAULT_VALIDATION_POLICY, PlanValidationResult, ValidationIssue, validate_plan
from semduck.errors import (
    SemanticCompileError,
    SemanticJoinError,
    SemanticParseError,
    SemanticRegistryError,
    SemanticResolutionError,
    SemanticUnsupportedError,
    SemanticViewError,
)
from semduck.llm import (
    create_provider_registry,
    load_llm_config,
    resolve_llm_log_dir,
    resolve_llm_task_configs,
)
from semduck.llm.config import ResolvedLLMConfig
from semduck.parser.request_parser import parse_request
from semduck.registry.reader import load_semantic_view_registry
from semduck.runtime.executor import compile_parsed_semantic_request
from semduck.types import ParsedSemanticRequest, RequestedOrderBy


ASK_PLAN_TASK = "ask_plan"
ASK_SUMMARY_TASK = "ask_summary"
TEXT_RESULT_ROW_LIMIT = 20
SQL_PREFIXES = ("select", "with", "insert", "update", "delete")
MODEL_MESSAGE_ADAPTER = TypeAdapter(ModelMessage)
NULLISH_WHERE_CLAUSES = {"none", "null", "nil", "n/a", "na"}
AskProgressReporter = Callable[[str], None]
AskOutput = Literal["sql", "table", "csv", "summary"]
DEFAULT_ASK_OUTPUTS: tuple[AskOutput, ...] = ("table",)
ALL_ASK_OUTPUTS: tuple[AskOutput, ...] = ("sql", "table", "csv", "summary")
QUALIFIED_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\b")


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
    order_by: list[str] = Field(default_factory=list)
    limit: int | None = None

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

    @field_validator("dimensions", "metrics", "order_by", mode="before")
    @classmethod
    def normalize_items(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("dimensions, metrics, and order_by must be lists of strings")

    @field_validator("where_clause")
    @classmethod
    def normalize_where_clause(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _normalize_nullish_token(value)
        if value.lower() in NULLISH_WHERE_CLAUSES:
            return None
        return value or None

    @field_validator("limit")
    @classmethod
    def normalize_limit(cls, value: int | str | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = _normalize_nullish_token(value)
            if value.lower() in NULLISH_WHERE_CLAUSES:
                return None
            if not value.isdigit():
                raise ValueError("limit must be a positive integer")
            value = int(value)
        if value <= 0:
            raise ValueError("limit must be a positive integer")
        return value

    @model_validator(mode="after")
    def validate_request_shape(self) -> "AskPlan":
        if self.chosen_view is None:
            if self.dimensions or self.metrics or self.order_by:
                raise ValueError("dimensions, metrics, and order_by must be empty when chosen_view is null")
            if self.where_clause is not None:
                raise ValueError("where_clause must be null when chosen_view is null")
            if self.limit is not None:
                raise ValueError("limit must be null when chosen_view is null")
            return self
        if not self.dimensions and not self.metrics:
            raise ValueError("at least one dimension or metric is required")
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
    order_by: list[str] = Field(default_factory=list)
    limit: int | None = None
    row_limit: int | None = None
    total_row_count: int = 0
    omitted_row_count: int = 0
    requested_outputs: list[AskOutput] = Field(default_factory=list)


class AskExecutionError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        troubleshooting: list[str] | None = None,
        *,
        failure_stage: str | None = None,
        attempts: list["AskAttemptTrace"] | None = None,
        validation_issues: list[ValidationIssue] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.troubleshooting = troubleshooting or []
        self.failure_stage = failure_stage
        self.attempts = attempts or []
        self.validation_issues = validation_issues or []


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


def _serialize_messages_safe(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        try:
            serialized.append(MODEL_MESSAGE_ADAPTER.dump_python(message, mode="json"))
        except Exception as exc:
            serialized.append(
                {
                    "part_kind": "serialization_error",
                    "message_index": index,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                    "message_type": type(message).__name__,
                    "message_repr": repr(message),
                }
            )
    return serialized


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
    include_summary: bool = False,
) -> tuple[AskStageModel, AskStageModel | None, Path | None]:
    llm_config = load_llm_config(config)
    task_names: tuple[str, ...] = (ASK_PLAN_TASK, ASK_SUMMARY_TASK) if include_summary else (ASK_PLAN_TASK,)
    resolved_tasks = resolve_llm_task_configs(
        llm_config,
        task_names=task_names,
        provider=provider,
        model=model,
    )
    registry = create_provider_registry()
    plan_config = resolved_tasks[ASK_PLAN_TASK]
    summary_config = resolved_tasks.get(ASK_SUMMARY_TASK)
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
        (
            AskStageModel(
                stage=ASK_SUMMARY_TASK,
                provider_name=summary_config.provider_name,
                model_name=summary_config.model,
                agent_model=registry.build_model(summary_config),
            )
            if summary_config is not None
            else None
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
            "Use --sql to inspect the generated semantic request and compiled SQL without executing the query.",
        ],
    )


def _error_code_for_semantic_error(exc: SemanticViewError) -> str:
    if isinstance(exc, SemanticRegistryError):
        return "registry"
    if isinstance(exc, SemanticUnsupportedError):
        return "unsupported"
    if isinstance(exc, (SemanticResolutionError, SemanticJoinError)):
        return "resolution"
    if isinstance(exc, SemanticCompileError):
        return "compile"
    if isinstance(exc, SemanticParseError):
        return "parse"
    return "compile"


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


def _parse_plan_order_by(order_by_items: list[str]) -> list[RequestedOrderBy]:
    parsed_items: list[RequestedOrderBy] = []
    for item in order_by_items:
        candidate = item.strip()
        if not candidate:
            continue
        tokens = candidate.rsplit(" ", 1)
        descending = False
        if len(tokens) == 2 and tokens[1].lower() in {"asc", "desc"}:
            candidate = tokens[0].strip()
            descending = tokens[1].lower() == "desc"
        if not candidate:
            raise ValueError(f"Malformed order_by item: {item}")
        parsed_items.append(RequestedOrderBy(name=candidate, descending=descending))
    return parsed_items


def _build_parsed_request(plan: AskPlan) -> ParsedSemanticRequest:
    semantic_request = _render_semantic_request(plan)
    parsed = parse_request(semantic_request)
    parsed.order_by = _parse_plan_order_by(plan.order_by)
    parsed.limit = plan.limit
    return parsed


def _normalize_plan_aliases(conn: Any, plan: AskPlan) -> AskPlan:
    if plan.chosen_view is None:
        return plan

    registry = load_semantic_view_registry(conn, plan.chosen_view)
    aliases = sorted(
        (table.alias for table in registry.tables.values() if table.alias),
        key=len,
        reverse=True,
    )
    normalized = plan.model_copy(deep=True)

    if aliases:
        alias_pattern = re.compile(
            rf"(?<![A-Za-z0-9_])(?:{'|'.join(re.escape(alias) for alias in aliases)})\.(?=[A-Za-z_])"
        )

        def strip_aliases(value: str | None) -> str | None:
            if value is None:
                return None
            return alias_pattern.sub("", value)

        normalized.dimensions = [strip_aliases(item) or "" for item in normalized.dimensions]
        normalized.metrics = [strip_aliases(item) or "" for item in normalized.metrics]
        normalized.order_by = [strip_aliases(item) or "" for item in normalized.order_by]
        normalized.where_clause = strip_aliases(normalized.where_clause)

    remaining_qualified_refs: list[str] = []
    for value in [
        *normalized.dimensions,
        *normalized.metrics,
        *normalized.order_by,
        *( [normalized.where_clause] if normalized.where_clause else [] ),
    ]:
        matches = QUALIFIED_IDENTIFIER_RE.findall(value)
        remaining_qualified_refs.extend(matches)

    if remaining_qualified_refs:
        refs = ", ".join(sorted(set(remaining_qualified_refs)))
        raise ValueError(
            "Plan contains table-qualified identifiers after normalization: "
            f"{refs}. Use semantic field names instead of table aliases."
        )

    return normalized


async def _run_agent(
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
            result = await agent.run(prompt, deps=deps)
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
                    messages=_serialize_messages_safe(messages),
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
        messages=_serialize_messages_safe(messages),
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
    )


def _validate_compilable_request(conn: Any, plan: AskPlan) -> None:
    parsed = _build_parsed_request(plan)
    compile_parsed_semantic_request(conn, parsed, request=_render_semantic_request(plan))


def _is_empty_plan(plan: AskPlan) -> bool:
    return (
        plan.chosen_view is None
        and not plan.dimensions
        and not plan.metrics
        and plan.where_clause is None
        and not plan.order_by
        and plan.limit is None
    )


def _null_plan() -> AskPlan:
    return AskPlan(
        chosen_view=None,
        dimensions=[],
        metrics=[],
        where_clause=None,
        order_by=[],
        limit=None,
    )


def _messages_show_successful_tool_inspection(messages: list[dict[str, Any]]) -> bool:
    def contains_tool_return(value: Any) -> bool:
        if isinstance(value, dict):
            if value.get("part_kind") == "tool-return":
                return True
            return any(contains_tool_return(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_tool_return(item) for item in value)
        return False

    return any(contains_tool_return(message) for message in messages)


def _is_output_validation_failure(exc: Exception) -> bool:
    message = str(exc).lower()
    return "output validation" in message or "invalid json" in message


def _build_retry_error_guidance(error: Exception) -> str:
    message = str(error).strip()
    lower_message = message.lower()
    guidance = [f"Validation error: {message}"]

    if "table-qualified identifiers" in lower_message:
        guidance.append(
            "Use semantic field names only. Remove table qualifiers such as products., orders., o., c., or p. "
            "For example, use is_active = false instead of products.is_active = false."
        )
    elif "semantic_request must be a semduck request, not raw sql" in lower_message:
        guidance.append("Do not return SQL. Return the structured object only.")
    elif "unsupported clause" in lower_message:
        guidance.append("Remove unsupported clauses and keep only chosen_view, dimensions, metrics, where_clause, order_by, and limit.")
    elif "at least one dimension or metric is required" in lower_message:
        guidance.append("Keep the chosen view only if at least one confirmed dimension or metric remains selected.")

    return "\n".join(guidance)


def _normalize_requested_outputs(
    *,
    include_sql: bool = False,
    include_table: bool = False,
    include_csv: bool = False,
    include_summary: bool = False,
) -> list[AskOutput]:
    requested_outputs: list[AskOutput] = []
    if include_sql:
        requested_outputs.append("sql")
    if include_table:
        requested_outputs.append("table")
    if include_csv:
        requested_outputs.append("csv")
    if include_summary:
        requested_outputs.append("summary")
    if not requested_outputs:
        return list(DEFAULT_ASK_OUTPUTS)
    return requested_outputs


async def _ask_with_semantic_retry(
    agent: Agent[AskDependencies, AskPlan],
    stage_model: AskStageModel,
    question: str,
    deps: AskDependencies,
    *,
    progress: AskProgressReporter | None = None,
) -> tuple[AskPlan, list[AskAttemptTrace], PlanValidationResult | None]:
    attempts: list[AskAttemptTrace] = []
    _emit_progress(progress, "planning semantic request")
    try:
        plan, initial_attempt = await _run_agent(agent, question, deps=deps, stage_model=stage_model)
    except AskAgentRunError as exc:
        attempts.append(exc.attempt)
        if _is_output_validation_failure(exc.cause) and _messages_show_successful_tool_inspection(exc.attempt.messages):
            return _null_plan(), attempts, None
        raise AskExecutionError(
            code="runtime",
            message=str(exc.cause),
            troubleshooting=_troubleshooting_for_error("runtime"),
            failure_stage=stage_model.stage,
            attempts=attempts,
        ) from exc.cause
    attempts.append(initial_attempt)
    if _is_empty_plan(plan):
        validation = validate_plan(
            question,
            plan,
            deps.conn,
            policy=DEFAULT_VALIDATION_POLICY,
        )
        if validation.action in {"accept", "accept_with_warnings"}:
            return plan, attempts, validation
        if validation.action == "reject_as_unsupported":
            return plan, attempts, validation
    else:
        try:
            plan = _normalize_plan_aliases(deps.conn, plan)
        except (ValueError, SemanticViewError):
            pass
        validation = validate_plan(
            question,
            plan,
            deps.conn,
            policy=DEFAULT_VALIDATION_POLICY,
        )
        if validation.action in {"accept", "accept_with_warnings"}:
            return validation.normalized_plan or plan, attempts, validation
        if validation.action == "reject_as_unsupported":
            return _null_plan(), attempts, validation

    if validation is None:
        validation = validate_plan(
            question,
            plan,
            deps.conn,
            policy=DEFAULT_VALIDATION_POLICY,
        )

    _emit_progress(progress, "retrying planner after validator rejection")
    retry_prompt = (
        f"{question}\n\n"
        "Fix the previous structured request.\n"
        f"Previous plan: chosen_view={plan.chosen_view!r}, dimensions={plan.dimensions!r}, "
        f"metrics={plan.metrics!r}, where_clause={plan.where_clause!r}, "
        f"order_by={plan.order_by!r}, limit={plan.limit!r}\n"
        f"{chr(10).join(validation.retry_feedback)}\n\n"
        "Preserve the valid parts of the previous plan and fix only the invalid field.\n"
        "If you cannot correct it without guessing, return the null plan.\n"
        "Return only one structured object with exactly these fields: chosen_view, dimensions, metrics, where_clause, order_by, limit.\n"
        "Do not output reasoning, prose, SQL, or code fences."
    )
    try:
        retry_plan, retry_attempt = await _run_agent(agent, retry_prompt, deps=deps, stage_model=stage_model)
    except AskAgentRunError as exc:
        exc.attempt.is_retry = True
        attempts.append(exc.attempt)
        return _null_plan(), attempts, validation
    retry_attempt.is_retry = True
    attempts.append(retry_attempt)
    if _is_empty_plan(retry_plan):
        retry_validation = validate_plan(
            question,
            retry_plan,
            deps.conn,
            policy=DEFAULT_VALIDATION_POLICY,
        )
        return retry_plan, attempts, retry_validation
    try:
        retry_plan = _normalize_plan_aliases(deps.conn, retry_plan)
    except (ValueError, SemanticViewError):
        pass
    retry_validation = validate_plan(
        question,
        retry_plan,
        deps.conn,
        policy=DEFAULT_VALIDATION_POLICY,
    )
    if retry_validation.action in {"accept", "accept_with_warnings"}:
        return retry_validation.normalized_plan or retry_plan, attempts, retry_validation
    return _null_plan(), attempts, retry_validation


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
    return _json_dumps(payload, indent=2)


def _json_dumps(payload: Any, *, indent: int | None = None, ensure_ascii: bool = True) -> str:
    return json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii, default=str)


async def _summarize_results(
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
        summary, attempt = await _run_agent(agent, prompt, deps=None, stage_model=stage_model)
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
    validation: PlanValidationResult | None = None,
    validation_timestamp: str | None = None,
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
        planner_attempts = [attempt for attempt in attempts if attempt.stage == ASK_PLAN_TASK]
        later_attempts = [attempt for attempt in attempts if attempt.stage != ASK_PLAN_TASK]

        for index, attempt in enumerate(planner_attempts, start=1):
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
            handle.write(_json_dumps(record, ensure_ascii=True) + "\n")

        if validation is not None:
            handle.write(
                _json_dumps(
                    {
                        **base_record,
                        "timestamp": validation_timestamp or datetime.now(UTC).isoformat(),
                        "event": "validation_result",
                        "validation": {
                            "action": validation.action,
                            "issues": [issue.model_dump() for issue in validation.issues],
                            "intent": validation.intent.model_dump() if validation.intent is not None else None,
                            "candidate_views": validation.candidate_views,
                            "normalized_plan": (
                                validation.normalized_plan.model_dump()
                                if hasattr(validation.normalized_plan, "model_dump")
                                else validation.normalized_plan
                            ),
                            "retry_feedback": validation.retry_feedback,
                        },
                    },
                )
                + "\n"
            )

        for index, attempt in enumerate(later_attempts, start=len(planner_attempts) + 1):
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
            handle.write(_json_dumps(record, ensure_ascii=True) + "\n")

        if result is not None:
            handle.write(
                _json_dumps(
                    {
                        **base_record,
                        "event": "ask_result",
                        "result": result.model_dump(),
                    },
                )
                + "\n"
            )
        if failure is not None:
            handle.write(
                _json_dumps(
                    {
                        **base_record,
                        "event": "ask_error",
                        "failure_stage": failure.failure_stage,
                        "error": {
                            "code": failure.code,
                            "message": failure.message,
                            "troubleshooting": failure.troubleshooting,
                            "validation_issues": [issue.model_dump() for issue in failure.validation_issues],
                        },
                    },
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
            "Use semduck tools to inspect available semantic views before returning a final answer. "
            "Your final answer must be one structured object with exactly these fields: chosen_view, dimensions, metrics, where_clause, order_by, limit. "
            "Do not return prose, summaries, SQL, markdown, code fences, reasoning, pseudo-tool text, or schema descriptions. "
            "Only use exact view names returned by list_semantic_views. "
            "Only use dimensions and metrics confirmed by describe_semantic_view. "
            "Treat a semantic view as answerable if one described view contains all requested dimensions and metrics anywhere in that view, including across joined tables. "
            "A single semantic view may satisfy a question using fields from different joined tables inside that view; this still counts as one view. "
            "Your only valid final actions are: choose one described semantic view, or return the null plan. "
            "Unsupported or ambiguous questions must still return the same structured object with chosen_view = null. "
            "Never return SQL, custom JSON, explanations, or hypothetical query plans instead of that object. "
            "Do not invent cross-view joins to rescue an unsupported question. "
            "Do not invent views, metrics, dimensions, joins, filters, or aliases. "
            "Preserve all clearly requested concepts from the question. Do not answer a partial question. "
            "Preserve the exact requested business measure. Do not substitute nearby metrics such as gross for net, revenue for profit, item sales for order sales, or average for total. "
            "Return chosen_view = null only when no single described semantic view contains all requested dimensions and metrics for the full question. "
            "Use semantic field names, not table aliases like o., c., or p., anywhere in dimensions, metrics, where_clause, or order_by. "
            "If the question specifies a time grain like day, week, month, quarter, or year, use date_trunc at that grain. "
            "If the question asks for a trend or says over time without specifying a grain, default to month when a suitable date dimension exists. "
            "If the question asks about a cohort, treat cohort as a grouped time bucket. For signup or acquisition cohorts, default to month unless another grain is explicitly requested. "
            "If no predicate is needed, where_clause must be null. "
            "If ranking is requested, populate order_by and optionally limit. Otherwise order_by must be []. "
            "order_by entries must reference selected outputs only. "
            "If no limit is needed, limit must be null. "
            "Examples: "
            "Question: 'Show the top 5 regions by revenue by month.' "
            "Return: "
            "{\"chosen_view\":\"orders\",\"dimensions\":[\"date_trunc('month', order_date) as order_month\",\"region\"],\"metrics\":[\"total_revenue\"],\"where_clause\":null,\"order_by\":[\"total_revenue desc\"],\"limit\":5} "
            "Question: 'How many orders come from each segment and sales channel combination?' "
            "Return: "
            "{\"chosen_view\":\"customer_semantic\",\"dimensions\":[\"segment_name\",\"sales_channel\"],\"metrics\":[\"order_count\"],\"where_clause\":null,\"order_by\":[],\"limit\":null}"
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
            "Inspect enough views to confirm coverage before you finalize a plan. "
            "Do not stop at the first plausible view if it drops a requested concept. "
            "Once one described semantic view clearly contains all requested concepts, choose it unless another described view is a strictly better fit. "
            "Prefer the smallest single semantic view that contains all requested concepts. "
            "Do not reject a valid view because the needed fields come from different joined tables inside that view. "
            "After inspecting the relevant views, stop. Your only valid final actions are: choose one described semantic view, or return the null plan. "
            "Do not invent cross-view joins, fallback SQL, or alternative output formats. "
            "If no single described semantic view covers the full question, return chosen_view = null with empty dimensions and metrics. "
            "If no semantic views are available, do not fabricate a request."
        )

    @agent.tool(sequential=True)
    def list_semantic_views(ctx: RunContext[AskDependencies]) -> list[str]:
        """List the semantic views available in the connected semduck registry."""
        return list_semantic_views_service(ctx.deps.conn).view_names

    @agent.tool(sequential=True)
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
            "Return either one concise sentence or one compact markdown table. "
            "If you return a table, it must use exactly the provided columns in the same order. "
            "Output only the final answer text. "
            "Do not show your reasoning, analysis, thinking process, draft text, or decision process. "
            "Do not invent rows, aggregations, or facts that are not present in the payload. "
            "Do not invent headings, category labels, or renamed columns. "
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


async def ask_question_async(
    conn_or_db: Any,
    question: str,
    *,
    config: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    view: str | None = None,
    row_limit: int | None = None,
    llm_log_dir: str | None = None,
    disable_llm_log: bool = False,
    include_sql: bool = False,
    include_table: bool = False,
    include_csv: bool = False,
    include_summary: bool = False,
    progress: AskProgressReporter | None = None,
) -> AskResult:
    attempts: list[AskAttemptTrace] = []
    resolved_log_dir: Path | None = None
    validation_result: PlanValidationResult | None = None
    validation_timestamp: str | None = None
    requested_outputs = _normalize_requested_outputs(
        include_sql=include_sql,
        include_table=include_table,
        include_csv=include_csv,
        include_summary=include_summary,
    )
    execute = any(output in {"table", "csv", "summary"} for output in requested_outputs)
    try:
        _emit_progress(progress, "resolving ask configuration")
        plan_stage, summary_stage, resolved_log_dir = _resolve_ask_models(
            config=config,
            provider=provider,
            model=model,
            llm_log_dir=llm_log_dir,
            disable_llm_log=disable_llm_log,
            include_summary="summary" in requested_outputs,
        )
        planner = create_ask_planner(plan_stage.agent_model)
        summary_agent = create_ask_summary_agent(summary_stage.agent_model) if summary_stage is not None else None
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
            plan, plan_attempts, validation_result = await _ask_with_semantic_retry(
                planner,
                plan_stage,
                question,
                deps,
                progress=progress,
            )
            attempts.extend(plan_attempts)
            if validation_result is not None:
                validation_timestamp = datetime.now(UTC).isoformat()
            if _is_empty_plan(plan):
                raise AskExecutionError(
                    code="unsupported",
                    message="The available semantic views cannot answer this question.",
                    troubleshooting=_troubleshooting_for_error("unsupported"),
                    failure_stage="validation",
                    validation_issues=validation_result.issues if validation_result is not None else [],
                )
            semantic_request = _render_semantic_request(plan)
            try:
                parsed_request = _build_parsed_request(plan)
            except (ValueError, SemanticViewError) as exc:
                raise AskExecutionError(
                    code="validation",
                    message=str(exc),
                    troubleshooting=_troubleshooting_for_error("validation"),
                    failure_stage="validation",
                    validation_issues=validation_result.issues if validation_result is not None else [],
                ) from exc

            _emit_progress(progress, "compiling semantic request")
            try:
                compiled = compile_parsed_semantic_request(
                    conn,
                    parsed_request,
                    request=semantic_request,
                )
            except SemanticViewError as exc:
                code = _error_code_for_semantic_error(exc)
                raise AskExecutionError(
                    code=code,
                    message=str(exc),
                    troubleshooting=_troubleshooting_for_error(code),
                    failure_stage="compile",
                ) from exc
            if view is not None and compiled.parsed_request.semantic_view_ref != view:
                raise AskExecutionError(
                    code="registry",
                    message=(
                        f"Ask planner selected semantic view {compiled.parsed_request.semantic_view_ref!r}, "
                        f"but {view!r} was explicitly requested."
                    ),
                    troubleshooting=_troubleshooting_for_error("registry"),
                    failure_stage="compile",
                )
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
                    relation = conn.sql(compiled.sql)
                    columns = [column[0] for column in relation.description]
                    query_rows = [list(row) for row in relation.fetchall()]
                except duckdb.Error as exc:
                    raise AskExecutionError(
                        code="runtime",
                        message=str(exc),
                        troubleshooting=_troubleshooting_for_error("runtime"),
                        failure_stage="execute",
                    ) from exc
                total_row_count = len(query_rows)
                if row_limit is not None and row_limit >= 0:
                    rows = query_rows[:row_limit]
                    omitted_row_count = max(total_row_count - len(rows), 0)
                else:
                    rows = query_rows
                if "summary" in requested_outputs:
                    _emit_progress(progress, "summarizing results")
                    if summary_agent is None or summary_stage is None:
                        raise AskExecutionError(
                            code="configuration",
                            message="Summary output requested but no summary model was resolved.",
                            troubleshooting=_troubleshooting_for_error("configuration"),
                            failure_stage=ASK_SUMMARY_TASK,
                        )
                    summary, summary_attempts = await _summarize_results(
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
                _emit_progress(progress, "skipping execution")

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
                chosen_view=compiled.parsed_request.semantic_view_ref,
                order_by=plan.order_by,
                limit=plan.limit,
                row_limit=row_limit,
                total_row_count=total_row_count,
                omitted_row_count=omitted_row_count,
                requested_outputs=requested_outputs,
            )
            _write_llm_trace(
                log_dir=resolved_log_dir,
                question=question,
                view=view,
                execute=execute,
                row_limit=row_limit,
                attempts=attempts,
                validation=validation_result,
                validation_timestamp=validation_timestamp,
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
                validation=validation_result,
                validation_timestamp=validation_timestamp,
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
                validation=validation_result,
                validation_timestamp=validation_timestamp,
                failure=failure,
            )
            raise failure from exc
    finally:
        if should_close:
            conn.close()


def ask_question(
    conn_or_db: Any,
    question: str,
    *,
    config: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    view: str | None = None,
    row_limit: int | None = None,
    llm_log_dir: str | None = None,
    disable_llm_log: bool = False,
    include_sql: bool = False,
    include_table: bool = False,
    include_csv: bool = False,
    include_summary: bool = False,
    progress: AskProgressReporter | None = None,
) -> AskResult:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            ask_question_async(
                conn_or_db,
                question,
                config=config,
                provider=provider,
                model=model,
                view=view,
                row_limit=row_limit,
                llm_log_dir=llm_log_dir,
                disable_llm_log=disable_llm_log,
                include_sql=include_sql,
                include_table=include_table,
                include_csv=include_csv,
                include_summary=include_summary,
                progress=progress,
            )
        )
    raise RuntimeError(
        "ask_question() cannot be used from an active event loop; use await ask_question_async(...) instead."
    )


def format_ask_result_text(result: AskResult) -> str:
    requested_outputs = getattr(result, "requested_outputs", None) or list(DEFAULT_ASK_OUTPUTS)
    sections: list[tuple[str, str]] = []
    if "sql" in requested_outputs:
        sections.append(("SQL", str(result.sql)))
    if "table" in requested_outputs:
        sections.append(("Table", _format_result_table(result)))
    if "csv" in requested_outputs:
        sections.append(("CSV", _format_result_csv(result)))
    if "summary" in requested_outputs:
        sections.append(("Summary", _format_result_summary(result)))

    if not sections:
        return _format_result_table(result)
    if len(sections) == 1:
        return sections[0][1]
    rendered_sections = [f"{title}:\n{content}" for title, content in sections]
    return "\n\n".join(rendered_sections)


def format_ask_result_json(result: AskResult) -> str:
    return _json_dumps(result.model_dump(), indent=2, ensure_ascii=False)


def _format_result_table(result: AskResult) -> str:
    if not result.executed:
        return "(execution skipped)"
    lines: list[str] = []
    if result.columns:
        lines.append(" | ".join(result.columns))
        display_rows = result.rows[:TEXT_RESULT_ROW_LIMIT]
        for row in display_rows:
            lines.append(" | ".join("" if value is None else str(value) for value in row))
        omitted_count = getattr(result, "omitted_row_count", max(len(result.rows) - len(display_rows), 0))
        if omitted_count > 0:
            lines.append(f"... {omitted_count} more rows omitted")
        return "\n".join(lines)
    return "(no rows)"


def _format_result_csv(result: AskResult) -> str:
    if not result.executed:
        return ""
    buffer = StringIO()
    writer = csv.writer(buffer)
    if result.columns:
        writer.writerow(result.columns)
        for row in result.rows:
            writer.writerow(row)
    return buffer.getvalue().rstrip("\r\n")


def _format_result_summary(result: AskResult) -> str:
    return str(result.answer_text)
