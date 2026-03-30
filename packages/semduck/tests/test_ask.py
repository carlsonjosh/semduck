from __future__ import annotations

from types import SimpleNamespace

from semduck.agent import AskPlan, ask_question, format_ask_result_text


class FakeAgent:
    def __init__(self, output: AskPlan):
        self._output = output

    def run_sync(self, question, *, deps):
        return SimpleNamespace(output=self._output)


def test_ask_question_executes_compiled_request(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_agent_model",
        lambda **kwargs: ("ollama", "llama3.1", object()),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_agent",
        lambda model: FakeAgent(
            AskPlan(
                answer_text="US revenue is 250.0",
                semantic_request="orders_semantic dimensions region metrics total_revenue where region = 'US'",
                chosen_view="orders_semantic",
            )
        ),
    )

    result = ask_question(loaded_conn, "What is US revenue?")

    assert result.executed is True
    assert result.provider == "ollama"
    assert result.model == "llama3.1"
    assert result.columns == ["region", "total_revenue"]
    assert result.rows == [["US", 250.0]]


def test_ask_question_sql_only_skips_execution(loaded_conn, monkeypatch):
    monkeypatch.setattr(
        "semduck.agent.ask._resolve_agent_model",
        lambda **kwargs: ("openai_compatible", "qwen2.5", object()),
    )
    monkeypatch.setattr(
        "semduck.agent.ask.create_ask_agent",
        lambda model: FakeAgent(
            AskPlan(
                answer_text="The query is ready.",
                semantic_request="orders_semantic dimensions region metrics total_revenue",
                chosen_view="orders_semantic",
            )
        ),
    )

    result = ask_question(loaded_conn, "Show revenue by region", execute=False)

    assert result.executed is False
    assert result.columns == []
    assert result.rows == []
    assert "select" in result.sql.lower()


def test_format_ask_result_text_includes_provenance():
    text = format_ask_result_text(
        result=SimpleNamespace(
            answer_text="US revenue is 250.0",
            chosen_view="orders_semantic",
            provider="ollama",
            model="llama3.1",
            semantic_request="orders_semantic dimensions region metrics total_revenue where region = 'US'",
            sql="select 1",
            executed=True,
            columns=["region", "total_revenue"],
            rows=[["US", 250.0]],
        )
    )

    assert "Answer: US revenue is 250.0" in text
    assert "Request: orders_semantic dimensions region metrics total_revenue where region = 'US'" in text
    assert "region | total_revenue" in text
