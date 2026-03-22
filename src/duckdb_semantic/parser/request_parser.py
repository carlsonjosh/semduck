from __future__ import annotations

import re

from duckdb_semantic.errors import SemanticParseError, SemanticUnsupportedError
from duckdb_semantic.types import ParsedSemanticRequest

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


def _parse_section(section_text: str) -> list[str]:
    return [item.strip() for item in section_text.split(",") if item.strip()]


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

    dimensions: list[str] = []
    metrics: list[str] = []
    where_clause = None

    for index, (keyword, position) in enumerate(ordered):
        start = position + len(f" {keyword} ")
        end = len(padded) - 1 if index == len(ordered) - 1 else ordered[index + 1][1] + 1
        section_text = padded[start:end].strip()

        if keyword == "dimensions":
            dimensions = _parse_section(section_text)
        elif keyword == "metrics":
            metrics = _parse_section(section_text)
        elif keyword == "where":
            where_clause = section_text or None

    return ParsedSemanticRequest(
        semantic_view_ref=semantic_view_ref,
        dimensions=dimensions,
        metrics=metrics,
        where_clause=where_clause,
    )

