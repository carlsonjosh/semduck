from __future__ import annotations

from types import SimpleNamespace

import pytest

from semduck.agent import AskExecutionError, AskPlan, ask_question, validate_plan


class SequencedFakeAgent:
    def __init__(self, outputs: list[object]):
        self._outputs = outputs
        self._index = 0

    async def run(self, question, *, deps):
        output = self._outputs[self._index]
        if self._index < len(self._outputs) - 1:
            self._index += 1
        return SimpleNamespace(output=output)


def fake_stage(stage: str, provider: str = "ollama", model: str = "llama3.1"):
    return SimpleNamespace(
        stage=stage,
        provider_name=provider,
        model_name=model,
        agent_model=object(),
    )


def test_validate_plan_rejects_wrong_metric_substitution(ecommerce_registry_conn):
    result = validate_plan(
        "Which payment methods are associated with the most product revenue?",
        AskPlan(
            chosen_view="orders_semantic",
            dimensions=["payment_method"],
            metrics=["net_sales"],
            order_by=["net_sales desc"],
        ),
        ecommerce_registry_conn,
    )

    assert result.action == "reject_for_retry"
    assert "product_sales_semantic" in result.candidate_views
    assert any(issue.code == "forbidden_metric_substitution" for issue in result.issues)
    assert any("product_sales_semantic" in line for line in result.retry_feedback)


def test_validate_plan_rejects_unsupported_dimension_substitution(ecommerce_registry_conn):
    result = validate_plan(
        "Which marketing campaigns drive the most net sales?",
        AskPlan(
            chosen_view="orders_semantic",
            dimensions=["sales_channel"],
            metrics=["net_sales"],
            order_by=["net_sales desc"],
        ),
        ecommerce_registry_conn,
    )

    assert result.action == "reject_as_unsupported"
    assert any(issue.code == "unsupported_question" for issue in result.issues)


def test_validate_plan_requests_retry_for_false_unsupported(ecommerce_registry_conn):
    result = validate_plan(
        "Which payment methods have the highest average order value?",
        AskPlan(
            chosen_view=None,
            dimensions=[],
            metrics=[],
            where_clause=None,
            order_by=[],
            limit=None,
        ),
        ecommerce_registry_conn,
    )

    assert result.action == "reject_for_retry"
    assert result.candidate_views == ["orders_semantic"]
    assert any(issue.code == "false_unsupported_candidate_exists" for issue in result.issues)


def test_validate_plan_requires_time_grain_for_month_question(loaded_conn):
    result = validate_plan(
        "Show total revenue by month.",
        AskPlan(
            chosen_view="orders_semantic",
            dimensions=["region"],
            metrics=["total_revenue"],
        ),
        loaded_conn,
    )

    assert result.action == "reject_for_retry"
    assert any(issue.code == "missing_time_grain" for issue in result.issues)


def test_validate_plan_accepts_signup_month_when_time_field_fallback_is_uncertain(ecommerce_registry_conn):
    result = validate_plan(
        "How many customers signed up each month?",
        AskPlan(
            chosen_view="customer_semantic",
            dimensions=["date_trunc('month', signup_date) as signup_month"],
            metrics=["customer_count"],
            order_by=["signup_month asc"],
        ),
        ecommerce_registry_conn,
    )

    assert result.action == "accept"
    assert result.intent.required_time_grain == "month"
    assert result.intent.required_time_dimension == "signup_date"
    assert result.intent.required_time_dimension_confident is True


def test_validate_plan_accepts_customer_state_without_requiring_state_synonym(ecommerce_registry_conn):
    result = validate_plan(
        "Rank customer states by net sales.",
        AskPlan(
            chosen_view="orders_semantic",
            dimensions=["customer_state"],
            metrics=["net_sales"],
            order_by=["net_sales desc"],
        ),
        ecommerce_registry_conn,
    )

    assert result.action == "accept"
    assert result.intent.required_dimensions == ["customer_state"]


def test_validate_plan_normalizes_unaliased_time_bucket_dimension(ecommerce_registry_conn):
    result = validate_plan(
        "What are net sales, order count, and average order value by month?",
        AskPlan(
            chosen_view="orders_semantic",
            dimensions=["date_trunc('month', order_date)"],
            metrics=["net_sales", "order_count", "average_order_value"],
            order_by=["date_trunc('month', order_date)"],
        ),
        ecommerce_registry_conn,
    )

    assert result.action == "accept"
    assert result.normalized_plan.dimensions == ["date_trunc('month', order_date) as order_month"]
    assert result.normalized_plan.order_by == ["order_month"]
    assert any(issue.code == "normalized_time_bucket_alias" for issue in result.issues)


def test_ask_question_retries_from_validator_feedback_before_compile(loaded_conn, monkeypatch):
    compile_calls = 0
    original_compile = __import__(
        "semduck.agent.ask",
        fromlist=["compile_parsed_semantic_request"],
    ).compile_parsed_semantic_request

    def counting_compile(conn, parsed, *, request=None):
        nonlocal compile_calls
        compile_calls += 1
        return original_compile(conn, parsed, request=request)

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
        lambda model: SequencedFakeAgent(
            [
                AskPlan(
                    chosen_view="orders_semantic",
                    dimensions=["region"],
                    metrics=["total_revenue"],
                ),
                AskPlan(
                    chosen_view="orders_semantic",
                    dimensions=["region"],
                    metrics=["total_revenue"],
                    order_by=["total_revenue desc"],
                ),
            ]
        ),
    )
    monkeypatch.setattr("semduck.agent.ask.compile_parsed_semantic_request", counting_compile)

    result = ask_question(
        loaded_conn,
        "Which regions have the highest total revenue?",
        include_sql=True,
    )

    assert compile_calls == 1
    assert result.order_by == ["total_revenue desc"]


def test_ask_question_surfaces_validation_issues_for_unsupported(ecommerce_registry_conn, monkeypatch):
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
        lambda model: SequencedFakeAgent(
            [
                AskPlan(
                    chosen_view="orders_semantic",
                    dimensions=["sales_channel"],
                    metrics=["net_sales"],
                    order_by=["net_sales desc"],
                )
            ]
        ),
    )

    with pytest.raises(AskExecutionError) as excinfo:
        ask_question(
            ecommerce_registry_conn,
            "Which marketing campaigns drive the most net sales?",
            include_sql=True,
        )

    assert excinfo.value.failure_stage == "validation"
    assert any(issue.code == "unsupported_question" for issue in excinfo.value.validation_issues)


def test_ask_question_normalizes_table_qualified_semantic_fields(ecommerce_registry_conn, monkeypatch):
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
        lambda model: SequencedFakeAgent(
            [
                AskPlan(
                    chosen_view="product_sales_semantic",
                    dimensions=["products.product_name"],
                    metrics=["order_items.net_item_sales"],
                    order_by=["order_items.net_item_sales desc"],
                )
            ]
        ),
    )

    result = ask_question(
        ecommerce_registry_conn,
        "Which products have the highest product revenue?",
        include_sql=True,
    )

    assert result.chosen_view == "product_sales_semantic"
    assert result.semantic_request == "product_sales_semantic dimensions product_name metrics net_item_sales"
    assert result.order_by == ["net_item_sales desc"]


def test_ask_question_retries_when_null_plan_has_false_unsupported_candidate(ecommerce_registry_conn, monkeypatch):
    compile_calls = 0
    original_compile = __import__(
        "semduck.agent.ask",
        fromlist=["compile_parsed_semantic_request"],
    ).compile_parsed_semantic_request

    def counting_compile(conn, parsed, *, request=None):
        nonlocal compile_calls
        compile_calls += 1
        return original_compile(conn, parsed, request=request)

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
        lambda model: SequencedFakeAgent(
            [
                AskPlan(
                    chosen_view=None,
                    dimensions=[],
                    metrics=[],
                    where_clause=None,
                    order_by=[],
                    limit=None,
                ),
                AskPlan(
                    chosen_view="customer_semantic",
                    dimensions=["date_trunc('month', signup_date) as signup_month"],
                    metrics=["lifetime_value"],
                    order_by=["signup_month asc"],
                    limit=None,
                ),
            ]
        ),
    )
    monkeypatch.setattr("semduck.agent.ask.compile_parsed_semantic_request", counting_compile)

    result = ask_question(
        ecommerce_registry_conn,
        "How does lifetime value vary by signup cohort?",
        include_sql=True,
    )

    assert compile_calls == 1
    assert result.chosen_view == "customer_semantic"
    assert result.semantic_request == (
        "customer_semantic dimensions date_trunc('month', signup_date) as signup_month "
        "metrics lifetime_value"
    )
