from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml

from semduck.errors import SemanticValidationError


def load_unresolved_dbt_spec(path: str) -> dict[str, Any]:
    spec = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise SemanticValidationError("YAML must define a mapping at the top level")
    return spec


def relation_map_from_json(relation_map_json: str) -> dict[str, dict[str, Any]]:
    relation_map = json.loads(relation_map_json)
    if not isinstance(relation_map, dict):
        raise SemanticValidationError("relation map must be a JSON object")
    return relation_map


def resolve_dbt_spec(spec: dict[str, Any], relation_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    resolved = copy.deepcopy(spec)
    tables = resolved.get("tables")
    if not isinstance(tables, list):
        return resolved

    for table_spec in tables:
        if not isinstance(table_spec, dict):
            continue
        base_table = table_spec.get("base_table")
        if not isinstance(base_table, dict):
            continue
        table_spec["base_table"] = _resolve_base_table(base_table, relation_map)
    return resolved


def _resolve_base_table(base_table: dict[str, Any], relation_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ref_name = base_table.get("ref")
    source_ref = base_table.get("source")
    has_direct_relation = base_table.get("table")

    if ref_name and (source_ref or has_direct_relation or base_table.get("schema")):
        raise SemanticValidationError("base_table.ref cannot be combined with direct relation fields")
    if source_ref and (has_direct_relation or base_table.get("schema") or ref_name):
        raise SemanticValidationError("base_table.source cannot be combined with direct relation fields")

    if ref_name:
        return _lookup_relation(f"ref:{ref_name}", relation_map)

    if source_ref:
        if not isinstance(source_ref, dict):
            raise SemanticValidationError("base_table.source must be a mapping")
        source_name = source_ref.get("name")
        table_name = source_ref.get("table")
        if not source_name or not table_name:
            raise SemanticValidationError("base_table.source requires name and table")
        return _lookup_relation(f"source:{source_name}.{table_name}", relation_map)

    return base_table


def _lookup_relation(key: str, relation_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    relation = relation_map.get(key)
    if relation is None:
        raise SemanticValidationError(f"Unable to resolve dbt relation: {key}")
    return relation
