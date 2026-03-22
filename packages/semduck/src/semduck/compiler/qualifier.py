from __future__ import annotations

import re

from semduck.types import SemanticObject

SQL_KEYWORDS = {
    "case",
    "when",
    "then",
    "else",
    "end",
    "and",
    "or",
    "not",
    "null",
    "is",
    "in",
    "like",
    "between",
    "sum",
    "avg",
    "min",
    "max",
    "count",
    "date_trunc",
    "coalesce",
    "cast",
    "as",
    "true",
    "false",
    "distinct",
}


def collect_expr_identifiers(expr: str) -> list[str]:
    tokens = re.split(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\W)", expr)
    names: list[str] = []
    for index, token in enumerate(tokens):
        stripped = token.strip()
        if not stripped:
            continue
        if (stripped.startswith("'") and stripped.endswith("'")) or (
            stripped.startswith('"') and stripped.endswith('"')
        ):
            continue
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", stripped):
            continue

        prev_token = tokens[index - 1] if index > 0 else ""
        next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
        next_non_space = next((item for item in tokens[index + 1 :] if item.strip()), "")

        if stripped.lower() in SQL_KEYWORDS:
            continue
        if prev_token == "." or next_token == "." or next_non_space == "(":
            continue
        if stripped not in names:
            names.append(stripped)
    return names


def rewrite_expr_identifiers(expr: str, replacements: dict[str, str], *, unknown_error: str | None = None) -> str:
    tokens = re.split(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|\W)", expr)
    out = []
    for index, token in enumerate(tokens):
        stripped = token.strip()
        if not stripped:
            out.append(token)
            continue
        if (stripped.startswith("'") and stripped.endswith("'")) or (
            stripped.startswith('"') and stripped.endswith('"')
        ):
            out.append(token)
            continue
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", stripped):
            out.append(token)
            continue

        prev_token = tokens[index - 1] if index > 0 else ""
        next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
        next_non_space = next((item for item in tokens[index + 1 :] if item.strip()), "")

        if stripped.lower() in SQL_KEYWORDS:
            out.append(token)
        elif prev_token == ".":
            out.append(token)
        elif next_token == ".":
            out.append(token)
        elif next_non_space == "(":
            out.append(token)
        elif stripped in replacements:
            out.append(replacements[stripped])
        elif unknown_error is not None:
            raise ValueError(unknown_error.format(name=stripped))
        else:
            out.append(token)
    return "".join(out)


def qualify_expr(expr: str, alias: str) -> str:
    class _PrefixedDict(dict):
        def __contains__(self, key):  # type: ignore[override]
            return True

        def __getitem__(self, key):  # type: ignore[override]
            return f"{alias}.{key}"

    return rewrite_expr_identifiers(expr, _PrefixedDict())


def qualify_metric_expr(metric: SemanticObject, alias: str) -> str:
    expr = metric.expr.strip()
    if metric.metric_type == "sum":
        return f"sum({qualify_expr(expr, alias)})"
    if metric.metric_type == "count":
        if expr == "*":
            return "count(*)"
        return f"count({qualify_expr(expr, alias)})"
    if metric.metric_type == "count_distinct":
        return f"count(distinct {qualify_expr(expr, alias)})"
    if metric.metric_type == "avg":
        return f"avg({qualify_expr(expr, alias)})"
    return qualify_expr(expr, alias)
