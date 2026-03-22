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


def qualify_expr(expr: str, alias: str) -> str:
    tokens = re.split(r"('(?:''|[^'])*'|\W)", expr)
    out = []
    for index, token in enumerate(tokens):
        stripped = token.strip()
        if not stripped:
            out.append(token)
            continue
        if stripped.startswith("'") and stripped.endswith("'"):
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
        else:
            out.append(f"{alias}.{token}")
    return "".join(out)


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
