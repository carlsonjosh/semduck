from semduck.errors import SemanticParseError, SemanticUnsupportedError
from semduck.parser.request_parser import parse_request
from semduck.types import DerivedDimension, DerivedMetric, NamedDimension, NamedMetric, RequestedOrderBy


def test_parse_name_only():
    parsed = parse_request("orders_semantic")
    assert parsed.semantic_view_ref == "orders_semantic"
    assert parsed.dimensions == []
    assert parsed.metrics == []
    assert parsed.where_clause is None


def test_parse_all_sections():
    parsed = parse_request(
        "orders_semantic dimensions region metrics total_revenue where region = 'US' order_by total_revenue desc limit 5"
    )
    assert parsed.semantic_view_ref == "orders_semantic"
    assert parsed.dimensions == [NamedDimension(name="region")]
    assert parsed.metrics == [NamedMetric(name="total_revenue")]
    assert parsed.where_clause == "region = 'US'"
    assert parsed.order_by == [RequestedOrderBy(name="total_revenue", descending=True)]
    assert parsed.limit == 5


def test_parse_nonstandard_order():
    parsed = parse_request("orders_semantic metrics total_revenue dimensions region")
    assert parsed.metrics == [NamedMetric(name="total_revenue")]
    assert parsed.dimensions == [NamedDimension(name="region")]


def test_parse_extra_whitespace():
    parsed = parse_request("  orders_semantic   dimensions  region, order_date   ")
    assert parsed.dimensions == [NamedDimension(name="region"), NamedDimension(name="order_date")]


def test_parse_empty_raises():
    try:
        parse_request("   ")
    except SemanticParseError:
        pass
    else:
        raise AssertionError("expected SemanticParseError")


def test_parse_unsupported_clause():
    try:
        parse_request("orders_semantic having total_revenue > 0")
    except SemanticUnsupportedError:
        pass
    else:
        raise AssertionError("expected SemanticUnsupportedError")


def test_parse_order_by_with_legacy_spacing():
    parsed = parse_request("orders_semantic dimensions region metrics total_revenue order by total_revenue desc")
    assert parsed.order_by == [RequestedOrderBy(name="total_revenue", descending=True)]


def test_parse_invalid_limit_rejected():
    try:
        parse_request("orders_semantic metrics total_revenue limit five")
    except SemanticParseError:
        pass
    else:
        raise AssertionError("expected SemanticParseError")


def test_parse_derived_dimension_and_metric():
    parsed = parse_request(
        "orders_semantic dimensions region, case when region = 'US' then 'domestic' else 'intl' end as market_type metrics total_revenue / 1000 as revenue_in_thousands"
    )
    assert parsed.dimensions == [
        NamedDimension(name="region"),
        DerivedDimension(
            expr="case when region = 'US' then 'domestic' else 'intl' end",
            alias="market_type",
        ),
    ]
    assert parsed.metrics == [
        DerivedMetric(expr="total_revenue / 1000", alias="revenue_in_thousands")
    ]


def test_parse_expression_without_alias_rejected():
    try:
        parse_request("orders_semantic metrics total_revenue / 1000")
    except SemanticParseError:
        pass
    else:
        raise AssertionError("expected SemanticParseError")
