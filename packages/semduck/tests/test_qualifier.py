from semduck.compiler.qualifier import qualify_expr, qualify_metric_expr
from semduck.types import SemanticObject


def test_qualify_bare_identifier():
    assert qualify_expr("region", "o") == "o.region"


def test_preserve_qualified_identifier():
    assert qualify_expr("o.region", "x") == "o.region"


def test_preserve_function_name():
    assert qualify_expr("date_trunc('day', order_date)", "o") == "date_trunc('day', o.order_date)"


def test_count_star_metric():
    metric = SemanticObject(name="row_count", object_type="metric", expr="*", metric_type="count")
    assert qualify_metric_expr(metric, "o") == "count(*)"


def test_preserve_string_literals():
    assert qualify_expr("case when region = 'US' then revenue else 0 end", "o") == (
        "case when o.region = 'US' then o.revenue else 0 end"
    )
