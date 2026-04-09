from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from semduck.agent import AskExecutionError, AskPlan, ask_question, ask_question_async, format_ask_result_json, format_ask_result_text
from semduck.agent.ask import AskAgentRunError, AskAttemptTrace, AskStageModel, _normalize_plan_aliases, _serialize_messages_safe
from semduck.errors import SemanticRegistryError


class FakeAgent:
    def __init__(self, output):
        self._output = output

    async def run(self, question, *, deps):
        return SimpleNamespace(output=self._output)


class SequencedFakeAgent:
    def __init__(self, outputs: list[object]):
        self._outputs = outputs
        self._index = 0

    async def run(self, question, *, deps):
        output = self._outputs[self._index]
        if self._index < len(self._outputs) - 1:
            self._index += 1
        return SimpleNamespace(output=output)


class RaisingFakeAgent:
    def __init__(self, error: Exception):
        self._error = error

    async def run(self, question, *, deps):
        raise self._error


def test_serialize_messages_safe_falls_back_on_serialization_error(monkeypatch):
    class DummyMessage:
        pass

    monkeypatch.setattr(
        "semduck.agent.ask.MODEL_MESSAGE_ADAPTER.dump_python",
        lambda message, mode: (_ for _ in ()).throw(ValueError("boom")),
    )

    serialized = _serialize_messages_safe([DummyMessage()])

    assert len(serialized) == 1
    assert serialized[0]["part_kind"] == "serialization_error"
    assert serialized[0]["error"]["type"] == "ValueError"
    assert serialized[0]["error"]["message"] == "boom"
    assert serialized[0]["message_type"] == "DummyMessage"


def test_normalize_plan_aliases_strips_known_table_aliases(loaded_conn):
    normalized = _normalize_plan_aliases(
        loaded_conn,
        AskPlan(
            chosen_view="orders_semantic",
            dimensions=["date_trunc('month', o.order_date) as order_month"],
            metrics=["total_shipping", "total_tax"],
            where_clause="o.order_status = 'completed'",
            order_by=["order_month asc"],
        ),
    )

    assert normalized.dimensions == ["date_trunc('month', order_date) as order_month"]
    assert normalized.where_clause == "order_status = 'completed'"


def test_normalize_plan_aliases_rejects_unknown_qualified_identifiers(loaded_conn):
    with pytest.raises(ValueError, match="table-qualified identifiers after normalization"):
        _normalize_plan_aliases(
            loaded_conn,
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["date_trunc('month', sales.order_date) as order_month"],
                metrics=["total_shipping"],
            ),
        )


def fake_stage(stage: str, provider: str = "ollama", model: str = "llama3.1") -> AskStageModel:
    return AskStageModel(
        stage=stage,
        provider_name=provider,
        model_name=model,
        agent_model=object(),
    )


def raw_plan(*, semantic_request: str):
    return AskPlan.model_construct(
        chosen_view=semantic_request,
        dimensions=[],
        metrics=[],
        where_clause=None,
    )


def test_ask_question_executes_compiled_request(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan", "ollama", "planner-model"),
            fake_stage("ask_summary", "openai_compatible", "summary-model"),
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
                where_clause="region = 'US'",
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent(
            "US revenue is 250.0"
        ),
    )

    result = ask_question(loaded_conn, "What is US revenue?", include_summary=True)

    assert result.executed is True
    assert result.provider == "ollama"
    assert result.model == "planner-model"
    assert result.summary_provider == "openai_compatible"
    assert result.summary_model == "summary-model"
    assert result.columns == ["region", "total_revenue"]
    assert result.rows == [["US", 250.0]]
    assert result.answer_text == "US revenue is 250.0"
    assert result.requested_outputs == ["summary"]


@pytest.mark.anyio
async def test_ask_question_async_executes_compiled_request(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan", "ollama", "planner-model"),
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent("unused"),
    )

    result = await ask_question_async(loaded_conn, "Show revenue by region")

    assert result.executed is True
    assert result.columns == ["region", "total_revenue"]


@pytest.mark.anyio
async def test_ask_question_raises_clear_error_in_active_event_loop(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan", "ollama", "planner-model"),
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent("unused"),
    )

    with pytest.raises(RuntimeError) as exc_info:
        ask_question(loaded_conn, "Show revenue by region")

    assert "ask_question_async" in str(exc_info.value)


def test_ask_question_executes_request_only_once(loaded_conn, monkeypatch):
    call_count = 0
    original_sql = type(loaded_conn).sql

    def counting_sql(conn, query):
        nonlocal call_count
        call_count += 1
        return original_sql(conn, query)

    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan"),
            fake_stage("ask_summary"),
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent(
            "Revenue by region is ready."
        ),
    )
    monkeypatch.setattr(type(loaded_conn), "sql", counting_sql)

    ask_question(loaded_conn, "Show revenue by region")

    assert call_count == 1


def test_ask_question_sql_only_skips_execution(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan", "openai_compatible", "planner-model"),
            fake_stage("ask_summary", "openai_compatible", "summary-model"),
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent(
            "unused"
        ),
    )

    result = ask_question(loaded_conn, "Show revenue by region", include_sql=True)

    assert result.executed is False
    assert result.columns == []
    assert result.rows == []
    assert result.summary_provider is None
    assert result.summary_model is None
    assert result.answer_text.startswith("Prepared semantic request without executing it:")
    assert "select" in result.sql.lower()
    assert result.requested_outputs == ["sql"]


def test_ask_question_applies_row_limit(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan"),
            fake_stage("ask_summary"),
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["customer_segment"],
                metrics=["total_revenue"],
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent(
            "Revenue by segment is ready."
        ),
    )

    result = ask_question(loaded_conn, "Show revenue by customer segment", row_limit=2)

    assert result.total_row_count == 3
    assert result.omitted_row_count == 1
    assert len(result.rows) == 2


def test_ask_question_writes_llm_trace_when_enabled(loaded_conn, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan", "ollama", "planner-model"),
            fake_stage("ask_summary", "openai_compatible", "summary-model"),
            tmp_path,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
                where_clause="region = 'US'",
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent(
            "US revenue is 250.0"
        ),
    )

    ask_question(loaded_conn, "What is US revenue?", include_summary=True)

    log_files = list(tmp_path.glob("ask-*.jsonl"))
    assert len(log_files) == 1
    records = [json.loads(line) for line in log_files[0].read_text(encoding="utf-8").splitlines()]
    assert records[0]["event"] == "ask_plan_attempt"
    assert records[0]["provider"] == "ollama"
    assert "started_at" in records[0]
    assert "finished_at" in records[0]
    assert isinstance(records[0]["duration_ms"], int)
    assert records[1]["event"] == "ask_summary_attempt"
    assert records[1]["provider"] == "openai_compatible"
    assert records[-1]["event"] == "ask_result"
    assert records[-1]["result"]["summary_model"] == "summary-model"


def test_ask_question_writes_partial_trace_for_planner_failure(loaded_conn, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan", "ollama", "planner-model"),
            fake_stage("ask_summary", "ollama", "summary-model"),
            tmp_path,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: RaisingFakeAgent(ValueError("Exceeded maximum retries (1) for output validation")),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent("unused"),
    )

    with pytest.raises(AskExecutionError) as excinfo:
        ask_question(loaded_conn, "What is total revenue by customer name?")

    assert excinfo.value.failure_stage == "ask_plan"

    log_files = list(tmp_path.glob("ask-*.jsonl"))
    assert len(log_files) == 1
    records = [json.loads(line) for line in log_files[0].read_text(encoding="utf-8").splitlines()]
    assert records[0]["event"] == "ask_plan_attempt"
    assert records[0]["output"]["error"]["message"] == "Exceeded maximum retries (1) for output validation"
    assert records[-1]["event"] == "ask_error"
    assert records[-1]["failure_stage"] == "ask_plan"


def test_ask_question_treats_planner_output_validation_failure_after_tool_use_as_unsupported(
    loaded_conn, monkeypatch
):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan", "ollama", "planner-model"),
            fake_stage("ask_summary", "ollama", "summary-model"),
            None,
        ),
    )
    monkeypatch.setattr("semduck.agent.ask.create_ask_planner", lambda model: object())
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent("unused"),
    )

    async def fake_run_agent(agent, prompt, *, deps, stage_model):
        raise AskAgentRunError(
            AskAttemptTrace(
                stage=stage_model.stage,
                prompt=prompt,
                provider=stage_model.provider_name,
                model=stage_model.model_name,
                output={"error": {"type": "ValueError", "message": "Exceeded maximum retries (1) for output validation"}},
                messages=[{"parts": [{"part_kind": "tool-return", "tool_name": "describe_semantic_view"}]}],
                started_at="2026-04-09T00:00:00+00:00",
                finished_at="2026-04-09T00:00:01+00:00",
                duration_ms=1000,
            ),
            ValueError("Exceeded maximum retries (1) for output validation"),
        )

    monkeypatch.setattr("semduck.agent.ask._run_agent", fake_run_agent)

    with pytest.raises(AskExecutionError) as excinfo:
        ask_question(loaded_conn, "What is total revenue by customer name?")

    assert excinfo.value.code == "unsupported"
    assert excinfo.value.failure_stage == "ask_plan"


def test_ask_question_writes_plan_attempts_for_compile_failure(loaded_conn, monkeypatch, tmp_path):
    call_count = 0
    original_compile = __import__(
        "semduck.agent.ask",
        fromlist=["compile_parsed_semantic_request"],
    ).compile_parsed_semantic_request

    def flaky_compile(conn, parsed, *, request=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return original_compile(conn, parsed, request=request)
        raise SemanticRegistryError("Unknown semantic view: orders ['customer_name'] ['total_revenue']")

    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan", "ollama", "planner-model"),
            fake_stage("ask_summary", "ollama", "summary-model"),
            tmp_path,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent("unused"),
    )
    monkeypatch.setattr("semduck.agent.ask.compile_parsed_semantic_request", flaky_compile)

    with pytest.raises(AskExecutionError) as excinfo:
        ask_question(loaded_conn, "What is total revenue by customer name?")

    assert excinfo.value.failure_stage == "compile"

    log_files = list(tmp_path.glob("ask-*.jsonl"))
    assert len(log_files) == 1
    records = [json.loads(line) for line in log_files[0].read_text(encoding="utf-8").splitlines()]
    assert records[0]["event"] == "ask_plan_attempt"
    assert records[0]["output"]["chosen_view"] == "orders_semantic"
    assert records[-1]["event"] == "ask_error"
    assert records[-1]["failure_stage"] == "compile"
    assert records[-1]["error"]["code"] == "registry"


def test_ask_plan_normalizes_nullish_where_clause_strings():
    plan = AskPlan(
        chosen_view="orders",
        dimensions=["customer_name"],
        metrics=["total_revenue"],
        where_clause="None",
    )

    assert plan.where_clause is None


def test_ask_plan_normalizes_wrapped_nullish_where_clause_strings():
    plan = AskPlan(
        chosen_view="orders",
        dimensions=["customer_name"],
        metrics=["total_revenue"],
        where_clause='["null"]',
    )

    assert plan.where_clause is None


def test_ask_plan_allows_null_chosen_view_when_request_is_empty():
    plan = AskPlan(
        chosen_view=None,
        dimensions=[],
        metrics=[],
        where_clause=None,
    )

    assert plan.chosen_view is None


def test_ask_plan_rejects_fields_when_chosen_view_is_null():
    with pytest.raises(ValueError, match="dimensions, metrics, and order_by must be empty"):
        AskPlan(
            chosen_view=None,
            dimensions=["region"],
            metrics=[],
            where_clause=None,
        )


def test_ask_question_treats_none_string_where_clause_as_missing(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan"),
            fake_stage("ask_summary"),
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
                where_clause="None",
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent(
            "unused"
        ),
    )

    result = ask_question(loaded_conn, "What is total revenue by region?", include_sql=True)

    assert result.semantic_request == "orders_semantic dimensions region metrics total_revenue"


def test_ask_question_raises_unsupported_error_when_no_semantic_views_are_available(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan"),
            fake_stage("ask_summary"),
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view=None,
                dimensions=[],
                metrics=[],
                where_clause=None,
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent("unused"),
    )

    with pytest.raises(AskExecutionError) as excinfo:
        ask_question(loaded_conn, "What is total revenue?")

    assert excinfo.value.code == "unsupported"
    assert excinfo.value.failure_stage == "ask_plan"
    assert "cannot answer this question" in excinfo.value.message


def test_ask_question_wraps_failures_with_troubleshooting(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan"),
            fake_stage("ask_summary"),
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="missing_view",
                metrics=["total_revenue"],
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent(
            "unused"
        ),
    )

    with pytest.raises(AskExecutionError) as excinfo:
        ask_question(loaded_conn, "What is revenue?")

    assert excinfo.value.code == "unsupported"
    assert excinfo.value.troubleshooting


def test_ask_question_retries_when_model_returns_sql(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan"),
            fake_stage("ask_summary"),
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: SequencedFakeAgent(
            [
                AskPlan(
                    chosen_view="orders_semantic",
                    dimensions=["region"],
                    metrics=["total_revenue"],
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent(
            "unused"
        ),
    )

    result = ask_question(loaded_conn, "Show revenue by region", include_sql=True)

    assert result.semantic_request == "orders_semantic dimensions region metrics total_revenue"
    assert "select" in result.sql.lower()


def test_ask_question_raises_parse_error_after_sql_retry(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan"),
            fake_stage("ask_summary"),
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: SequencedFakeAgent(
            [
                raw_plan(
                    semantic_request="SELECT region, sum(revenue) FROM orders GROUP BY region",
                ),
                raw_plan(
                    semantic_request="WITH revenue AS (SELECT * FROM orders) SELECT * FROM revenue",
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent(
            "unused"
        ),
    )

    with pytest.raises(AskExecutionError) as excinfo:
        ask_question(loaded_conn, "Show revenue by region", include_sql=True)

    assert excinfo.value.code == "unsupported"
    assert excinfo.value.troubleshooting


def test_ask_question_compiles_ordering_from_structured_plan(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan"),
            fake_stage("ask_summary"),
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
                order_by=["total_revenue desc"],
                limit=1,
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent(
            "unused"
        ),
    )

    result = ask_question(loaded_conn, "Show revenue by region", include_sql=True)

    assert result.semantic_request == "orders_semantic dimensions region metrics total_revenue"
    assert result.order_by == ["total_revenue desc"]
    assert result.limit == 1
    assert "order by total_revenue desc" in result.sql.lower()
    assert "limit 1" in result.sql.lower()

def test_ask_question_returns_clean_unsupported_error_for_null_view(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan"),
            fake_stage("ask_summary"),
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view=None,
                dimensions=[],
                metrics=[],
                where_clause=None,
                order_by=[],
                limit=None,
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent(
            "unused"
        ),
    )

    with pytest.raises(AskExecutionError) as excinfo:
        ask_question(loaded_conn, "Show revenue by region", include_sql=True)

    assert excinfo.value.code == "unsupported"
    assert excinfo.value.troubleshooting


def test_ask_question_retries_when_model_omits_request_keywords(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan"),
            fake_stage("ask_summary"),
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: SequencedFakeAgent(
            [
                raw_plan(
                    semantic_request="orders customer_segment total_revenue",
                ),
                AskPlan(
                    chosen_view="orders_semantic",
                    dimensions=["customer_segment"],
                    metrics=["total_revenue"],
                ),
            ]
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent(
            "unused"
        ),
    )

    result = ask_question(loaded_conn, "What is total revenue by customer segment?", include_sql=True)

    assert result.semantic_request == "orders_semantic dimensions customer_segment metrics total_revenue"


def test_format_ask_result_text_summary_only_returns_answer_text():
    text = format_ask_result_text(
        result=SimpleNamespace(
            answer_text="US revenue is 250.0",
            chosen_view="orders_semantic",
            provider="ollama",
            model="planner-model",
            summary_provider="openai_compatible",
            summary_model="summary-model",
            semantic_request="orders_semantic dimensions region metrics total_revenue where region = 'US'",
            sql="select 1",
            executed=True,
            requested_outputs=["summary"],
            columns=["region", "total_revenue"],
            rows=[["US", 250.0]],
        )
    )

    assert text == "US revenue is 250.0"


def test_format_ask_result_text_truncates_large_result_sets():
    rows = [[f"customer_{index}", float(index)] for index in range(25)]
    text = format_ask_result_text(
        result=SimpleNamespace(
            answer_text="Top customers shown below.",
            chosen_view="orders_semantic",
            provider="ollama",
            model="planner-model",
            summary_provider="openai_compatible",
            summary_model="summary-model",
            semantic_request="orders_semantic dimensions customer_name metrics total_revenue",
            sql="select 1",
            executed=True,
            requested_outputs=["table"],
            row_limit=20,
            total_row_count=25,
            omitted_row_count=5,
            columns=["customer_name", "total_revenue"],
            rows=rows,
        )
    )

    assert "customer_0 | 0.0" in text
    assert "customer_19 | 19.0" in text
    assert "customer_20 | 20.0" not in text
    assert "... 5 more rows omitted" in text


def test_ask_question_default_output_is_table_without_summary(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan", "ollama", "planner-model"),
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent("unused"),
    )

    result = ask_question(loaded_conn, "Show revenue by region")

    assert result.executed is True
    assert result.requested_outputs == ["table"]
    assert result.summary_provider is None
    assert result.summary_model is None


def test_ask_question_combines_sql_and_csv_without_summary(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan", "ollama", "planner-model"),
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent("unused"),
    )

    result = ask_question(loaded_conn, "Show revenue by region", include_sql=True, include_csv=True)

    assert result.executed is True
    assert result.requested_outputs == ["sql", "csv"]
    assert result.summary_provider is None
    assert result.summary_model is None


def test_ask_question_enforces_explicit_requested_view(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan"),
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent("unused"),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.compile_parsed_semantic_request",
        lambda conn, parsed, request=None: SimpleNamespace(
            request=request or parsed.semantic_view_ref,
            parsed_request=SimpleNamespace(semantic_view_ref="customers_semantic"),
            sql="select 1",
        ),
    )

    with pytest.raises(AskExecutionError) as exc_info:
        ask_question(
            loaded_conn,
            "Show revenue by region",
            view="orders_semantic",
            include_sql=True,
        )

    assert exc_info.value.code == "registry"
    assert "explicitly requested" in exc_info.value.message


def test_format_ask_result_text_renders_multiple_sections_in_order():
    text = format_ask_result_text(
        result=SimpleNamespace(
            answer_text="unused",
            chosen_view="orders_semantic",
            provider="ollama",
            model="planner-model",
            semantic_request="orders_semantic dimensions region metrics total_revenue",
            sql="select 1",
            executed=True,
            requested_outputs=["sql", "csv"],
            columns=["region", "total_revenue"],
            rows=[["US", 250.0]],
        )
    )

    assert text.startswith("SQL:\nselect 1\n\nCSV:\nregion,total_revenue")


def test_format_ask_result_json_serializes_common_duckdb_value_types():
    payload = json.loads(
        format_ask_result_json(
            SimpleNamespace(
                model_dump=lambda: {
                    "answer_text": "ok",
                    "rows": [[date(2024, 1, 2), Decimal("12.34")]],
                    "columns": ["day", "amount"],
                }
            )
        )
    )

    assert payload["rows"] == [["2024-01-02", "12.34"]]


def test_ask_question_writes_llm_trace_with_non_json_result_values(loaded_conn, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_ask_models",
        lambda **kwargs: (
            fake_stage("ask_plan", "ollama", "planner-model"),
            None,
            tmp_path,
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_planner",
        lambda model: FakeAgent(
            AskPlan(
                chosen_view="orders_semantic",
                dimensions=["region"],
                metrics=["total_revenue"],
            )
        ),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_summary_agent",
        lambda model: FakeAgent("unused"),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.compile_parsed_semantic_request",
        lambda conn, parsed, request=None: SimpleNamespace(
            request=request or parsed.semantic_view_ref,
            parsed_request=SimpleNamespace(semantic_view_ref=parsed.semantic_view_ref),
            sql="select 1",
        ),
    )
    monkeypatch.setattr(
        type(loaded_conn),
        "sql",
        lambda conn, query: SimpleNamespace(
            description=[("day",), ("amount",)],
            fetchall=lambda: [(date(2024, 1, 2), Decimal("12.34"))],
        ),
    )

    result = ask_question(loaded_conn, "Show revenue by region", include_table=True)

    assert result.rows == [[date(2024, 1, 2), Decimal("12.34")]]
    log_files = list(tmp_path.glob("ask-*.jsonl"))
    assert len(log_files) == 1
    records = [json.loads(line) for line in log_files[0].read_text(encoding="utf-8").splitlines()]
    assert records[-1]["event"] == "ask_result"
    assert records[-1]["result"]["rows"] == [["2024-01-02", "12.34"]]
