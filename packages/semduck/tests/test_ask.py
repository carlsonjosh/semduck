from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from semduck.agent import AskExecutionError, AskPlan, ask_question, format_ask_result_text
from semduck.agent.ask import AskStageModel


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

    result = ask_question(loaded_conn, "What is US revenue?")

    assert result.executed is True
    assert result.provider == "ollama"
    assert result.model == "planner-model"
    assert result.summary_provider == "openai_compatible"
    assert result.summary_model == "summary-model"
    assert result.columns == ["region", "total_revenue"]
    assert result.rows == [["US", 250.0]]
    assert result.answer_text == "US revenue is 250.0"


def test_ask_question_executes_request_only_once(loaded_conn, monkeypatch):
    call_count = 0
    original_query = __import__("semduck.agent.ask", fromlist=["query_request_service"]).query_request_service

    def counting_query(conn, args):
        nonlocal call_count
        call_count += 1
        return original_query(conn, args)

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
    monkeypatch.setattr("semduck.agent.ask.query_request_service", counting_query)

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

    result = ask_question(loaded_conn, "Show revenue by region", execute=False)

    assert result.executed is False
    assert result.columns == []
    assert result.rows == []
    assert result.summary_provider is None
    assert result.summary_model is None
    assert result.answer_text.startswith("Prepared semantic request without executing it:")
    assert "select" in result.sql.lower()


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

    ask_question(loaded_conn, "What is US revenue?")

    log_files = list(tmp_path.glob("ask-*.jsonl"))
    assert len(log_files) == 1
    records = [json.loads(line) for line in log_files[0].read_text(encoding="utf-8").splitlines()]
    assert records[0]["event"] == "ask_plan_attempt"
    assert records[0]["provider"] == "ollama"
    assert records[1]["event"] == "ask_summary_attempt"
    assert records[1]["provider"] == "openai_compatible"
    assert records[-1]["event"] == "ask_result"
    assert records[-1]["result"]["summary_model"] == "summary-model"


def test_ask_plan_normalizes_nullish_where_clause_strings():
    plan = AskPlan(
        chosen_view="orders",
        dimensions=["customer_name"],
        metrics=["total_revenue"],
        where_clause="None",
    )

    assert plan.where_clause is None


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

    result = ask_question(loaded_conn, "What is total revenue by region?", execute=False)

    assert result.semantic_request == "orders_semantic dimensions region metrics total_revenue"


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

    assert excinfo.value.code == "registry"
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

    result = ask_question(loaded_conn, "Show revenue by region", execute=False)

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
        ask_question(loaded_conn, "Show revenue by region", execute=False)

    assert excinfo.value.code == "parse"
    assert excinfo.value.troubleshooting


def test_ask_question_retries_when_model_returns_unsupported_clause(loaded_conn, monkeypatch):
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
                    semantic_request="orders_semantic dimensions region metrics total_revenue order by total_revenue desc",
                ),
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

    result = ask_question(loaded_conn, "Show revenue by region", execute=False)

    assert result.semantic_request == "orders_semantic dimensions region metrics total_revenue"


def test_ask_question_raises_unsupported_error_after_clause_retry(loaded_conn, monkeypatch):
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
                    semantic_request="orders_semantic dimensions region metrics total_revenue order by total_revenue desc",
                ),
                raw_plan(
                    semantic_request="orders_semantic dimensions region metrics total_revenue limit 10",
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
        ask_question(loaded_conn, "Show revenue by region", execute=False)

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

    result = ask_question(loaded_conn, "What is total revenue by customer segment?", execute=False)

    assert result.semantic_request == "orders_semantic dimensions customer_segment metrics total_revenue"


def test_format_ask_result_text_includes_provenance():
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
            columns=["region", "total_revenue"],
            rows=[["US", 250.0]],
        )
    )

    assert "Answer: US revenue is 250.0" in text
    assert "Provider: ollama" in text
    assert "Summary Provider: openai_compatible" in text
    assert "Request: orders_semantic dimensions region metrics total_revenue where region = 'US'" in text
    assert "region | total_revenue" in text


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
