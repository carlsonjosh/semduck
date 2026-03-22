from __future__ import annotations

import re

from duckdb_semantic.compiler.qualifier import qualify_expr
from duckdb_semantic.errors import SemanticResolutionError
from duckdb_semantic.types import SemanticViewRegistry


def build_name_lookup(registry: SemanticViewRegistry) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for table in registry.tables.values():
        for dim_name, dim in table.dimensions.items():
            if dim_name in lookup:
                raise SemanticResolutionError(f"Ambiguous where-clause identifier: {dim_name}")
            lookup[dim_name] = f"({qualify_expr(dim.expr, table.alias)})"
        for fact_name, fact in table.facts.items():
            if fact_name in lookup:
                raise SemanticResolutionError(f"Ambiguous where-clause identifier: {fact_name}")
            lookup[fact_name] = f"({qualify_expr(fact.expr, table.alias)})"
    return lookup


def _find_metrics(where_clause: str, registry: SemanticViewRegistry) -> list[str]:
    metric_names = set()
    for table in registry.tables.values():
        metric_names.update(table.metrics.keys())

    hits = []
    for name in metric_names:
        if re.search(rf"\b{re.escape(name)}\b", where_clause):
            hits.append(name)
    return sorted(hits)


def rewrite_where_clause(where_clause: str, registry: SemanticViewRegistry) -> str:
    metric_hits = _find_metrics(where_clause, registry)
    if metric_hits:
        raise SemanticResolutionError(f"Metric referenced in where clause: {', '.join(metric_hits)}")

    lookup = build_name_lookup(registry)
    rewritten = where_clause
    for name in sorted(lookup.keys(), key=len, reverse=True):
        rewritten = re.sub(rf"\b{re.escape(name)}\b", lookup[name], rewritten)
    return rewritten

