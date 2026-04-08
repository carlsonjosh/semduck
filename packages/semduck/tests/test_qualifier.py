from semduck.compiler.qualifier import contains_aggregate_function, qualify_expr


def test_qualify_bare_identifier():
    assert qualify_expr("region", "o") == "o.region"


def test_preserve_qualified_identifier():
    assert qualify_expr("o.region", "x") == "o.region"


def test_preserve_function_name():
    assert qualify_expr("date_trunc('day', order_date)", "o") == "date_trunc('day', o.order_date)"


def test_detect_aggregate_function():
    assert contains_aggregate_function("count(*)") is True
    assert contains_aggregate_function("sum(order_total) / count(order_id)") is True
    assert contains_aggregate_function("total_revenue / order_count") is False


def test_preserve_string_literals():
    assert qualify_expr("case when region = 'US' then revenue else 0 end", "o") == (
        "case when o.region = 'US' then o.revenue else 0 end"
    )
