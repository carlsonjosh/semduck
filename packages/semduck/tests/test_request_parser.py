from semduck.errors import SemanticParseError, SemanticUnsupportedError
from semduck.parser.request_parser import parse_request


def test_parse_name_only():
    parsed = parse_request("orders_semantic")
    assert parsed.semantic_view_ref == "orders_semantic"
    assert parsed.dimensions == []
    assert parsed.metrics == []
    assert parsed.where_clause is None


def test_parse_all_sections():
    parsed = parse_request("orders_semantic dimensions region metrics total_revenue where region = 'US'")
    assert parsed.semantic_view_ref == "orders_semantic"
    assert parsed.dimensions == ["region"]
    assert parsed.metrics == ["total_revenue"]
    assert parsed.where_clause == "region = 'US'"


def test_parse_nonstandard_order():
    parsed = parse_request("orders_semantic metrics total_revenue dimensions region")
    assert parsed.metrics == ["total_revenue"]
    assert parsed.dimensions == ["region"]


def test_parse_extra_whitespace():
    parsed = parse_request("  orders_semantic   dimensions  region, order_date   ")
    assert parsed.dimensions == ["region", "order_date"]


def test_parse_empty_raises():
    try:
        parse_request("   ")
    except SemanticParseError:
        pass
    else:
        raise AssertionError("expected SemanticParseError")


def test_parse_unsupported_clause():
    try:
        parse_request("orders_semantic order by region")
    except SemanticUnsupportedError:
        pass
    else:
        raise AssertionError("expected SemanticUnsupportedError")
