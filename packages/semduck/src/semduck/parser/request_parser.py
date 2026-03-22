from __future__ import annotations

import re

from semduck.errors import SemanticParseError, SemanticUnsupportedError
from semduck.types import (
    DerivedDimension,
    DerivedMetric,
    NamedDimension,
    NamedMetric,
    ParsedSemanticRequest,
    RequestedDimension,
    RequestedMetric,
)

SECTION_KEYWORDS = ("dimensions", "metrics", "where")
UNSUPPORTED_PATTERNS = (r"\bhaving\b", r"\border\s+by\b", r"\blimit\b")


def normalize_whitespace(value: str) -> str:
    return " ".join(value.strip().split())


def _check_unsupported(request: str) -> None:
    lowered = request.lower()
    for pattern in UNSUPPORTED_PATTERNS:
        if re.search(pattern, lowered):
            raise SemanticUnsupportedError(f"Unsupported clause in semantic request: {pattern.replace('\\b', '')}")


def find_keyword_positions(request: str) -> dict[str, int]:
    lowered = f" {request.lower()} "
    positions = {}
    for keyword in SECTION_KEYWORDS:
        token = f" {keyword} "
        index = lowered.find(token)
        if index != -1:
            positions[keyword] = index
    return positions


def _split_top_level_commas(section_text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0
    in_single = False
    in_double = False

    for ch in section_text:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "(" and not in_single and not in_double:
            depth += 1
        elif ch == ")" and not in_single and not in_double:
            depth -= 1
        elif ch == "," and depth == 0 and not in_single and not in_double:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
            continue
        current.append(ch)

    item = "".join(current).strip()
    if item:
        items.append(item)
    return items


def _split_alias(item: str) -> tuple[str, str | None]:
    lowered = item.lower()
    depth = 0
    in_single = False
    in_double = False
    alias_index: int | None = None

    for index, ch in enumerate(item):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "(" and not in_single and not in_double:
            depth += 1
        elif ch == ")" and not in_single and not in_double:
            depth -= 1
        elif depth == 0 and not in_single and not in_double:
            if lowered.startswith(" as ", index):
                alias_index = index

    if alias_index is None:
        return item.strip(), None

    expr = item[:alias_index].strip()
    alias = item[alias_index + 4 :].strip()
    if not expr or not alias:
        raise SemanticParseError(f"Malformed aliased expression: {item}")
    return expr, alias


def _parse_dimension_item(item: str) -> RequestedDimension:
    expr, alias = _split_alias(item)
    if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", expr) and alias is None:
        return NamedDimension(name=expr)
    if alias is None:
        raise SemanticParseError(f"Derived dimension expression requires alias: {item}")
    return DerivedDimension(expr=expr, alias=alias)


def _parse_metric_item(item: str) -> RequestedMetric:
    expr, alias = _split_alias(item)
    if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", expr) and alias is None:
        return NamedMetric(name=expr)
    if alias is None:
        raise SemanticParseError(f"Derived metric expression requires alias: {item}")
    return DerivedMetric(expr=expr, alias=alias)


def parse_request(request_str: str) -> ParsedSemanticRequest:
    raw = normalize_whitespace(request_str)
    if not raw:
        raise SemanticParseError("semantic request must not be empty")

    _check_unsupported(raw)

    padded = f" {raw} "
    positions = find_keyword_positions(raw)
    ordered = sorted(positions.items(), key=lambda item: item[1])

    if not ordered:
        return ParsedSemanticRequest(semantic_view_ref=raw)

    first_keyword, first_position = ordered[0]
    semantic_view_ref = padded[1:first_position + 1].strip()
    if not semantic_view_ref:
        raise SemanticParseError("semantic request missing semantic view reference")

    dimensions: list[RequestedDimension] = []
    metrics: list[RequestedMetric] = []
    where_clause = None

    for index, (keyword, position) in enumerate(ordered):
        start = position + len(f" {keyword} ")
        end = len(padded) - 1 if index == len(ordered) - 1 else ordered[index + 1][1] + 1
        section_text = padded[start:end].strip()

        if keyword == "dimensions":
            dimensions = [_parse_dimension_item(item) for item in _split_top_level_commas(section_text)]
        elif keyword == "metrics":
            metrics = [_parse_metric_item(item) for item in _split_top_level_commas(section_text)]
        elif keyword == "where":
            where_clause = section_text or None

    return ParsedSemanticRequest(
        semantic_view_ref=semantic_view_ref,
        dimensions=dimensions,
        metrics=metrics,
        where_clause=where_clause,
    )
