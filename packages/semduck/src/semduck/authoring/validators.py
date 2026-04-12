from __future__ import annotations

from typing import Any

from semduck.errors import SemanticValidationError


def build_table_alias(table_name: str, used_aliases: set[str]) -> str:
    cleaned = "".join(ch for ch in table_name if ch.isalnum() or ch == "_")
    base = (cleaned[:1] or "t").lower()
    alias = base
    index = 2
    while alias in used_aliases:
        alias = f"{base}{index}"
        index += 1
    used_aliases.add(alias)
    return alias


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SemanticValidationError(f"{label} must be a mapping")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SemanticValidationError(f"{label} must be a list")
    return value


def _validate_json_like(value: Any, label: str) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise SemanticValidationError(f"{label} keys must be strings")
            _validate_json_like(nested, label)
        return
    if isinstance(value, list):
        for nested in value:
            _validate_json_like(nested, label)
        return
    if isinstance(value, (str, int, float, bool)):
        return
    raise SemanticValidationError(f"{label} must contain only JSON-like values")


def _validate_ai_context(value: Any, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise SemanticValidationError(f"{label} ai_context must be a mapping")
    _validate_json_like(value, f"{label} ai_context")
    if "phrases" in value:
        phrases = value["phrases"]
        if not isinstance(phrases, list) or any(not isinstance(item, str) or not item.strip() for item in phrases):
            raise SemanticValidationError(f"{label} ai_context phrases must be a list of non-empty strings")
    if "concept_id" in value and (not isinstance(value["concept_id"], str) or not value["concept_id"].strip()):
        raise SemanticValidationError(f"{label} ai_context concept_id must be a non-empty string")
    if "concepts" in value:
        concepts = value["concepts"]
        if not isinstance(concepts, list):
            raise SemanticValidationError(f"{label} ai_context concepts must be a list")
        for index, concept in enumerate(concepts):
            if not isinstance(concept, dict):
                raise SemanticValidationError(f"{label} ai_context concepts[{index}] must be a mapping")
            concept_id = concept.get("concept_id")
            if not isinstance(concept_id, str) or not concept_id.strip():
                raise SemanticValidationError(f"{label} ai_context concepts[{index}] missing concept_id")
            concept_kind = concept.get("concept_kind")
            if concept_kind is not None and (not isinstance(concept_kind, str) or not concept_kind.strip()):
                raise SemanticValidationError(f"{label} ai_context concepts[{index}] concept_kind must be a string")
            _validate_json_like(concept, f"{label} ai_context concepts[{index}]")


def _validate_named_expr_objects(items: list[dict[str, Any]], label: str) -> None:
    seen = set()
    for item in items:
        obj = _require_mapping(item, label)
        name = obj.get("name")
        expr = obj.get("expr")
        if not name:
            raise SemanticValidationError(f"{label} item missing name")
        if name in seen:
            raise SemanticValidationError(f"Duplicate {label} name: {name}")
        if not expr:
            raise SemanticValidationError(f"{label} {name} missing expr")
        _validate_ai_context(obj.get("ai_context"), label)
        seen.add(name)


def _validate_metrics(metrics: list[dict[str, Any]]) -> None:
    seen = set()
    for metric in metrics:
        obj = _require_mapping(metric, "metrics")
        name = obj.get("name")
        expr = obj.get("expr")
        if not name:
            raise SemanticValidationError("metrics item missing name")
        if name in seen:
            raise SemanticValidationError(f"Duplicate metrics name: {name}")
        if not expr:
            raise SemanticValidationError(f"metric {name} missing expr")
        if "metric_type" in obj:
            raise SemanticValidationError(f"metric {name} must not define metric_type")
        if "default_agg" in obj:
            raise SemanticValidationError(f"metric {name} must not define default_agg")
        _validate_ai_context(obj.get("ai_context"), "metrics")
        seen.add(name)


def validate_semantic_spec(spec: dict[str, Any]) -> None:
    if not spec.get("name"):
        raise SemanticValidationError("semantic view must have a name")
    _validate_ai_context(spec.get("ai_context"), "semantic view")

    tables = _require_list(spec.get("tables"), "tables")
    if not tables:
        raise SemanticValidationError("semantic view must define at least one table")

    table_names = set()
    used_aliases = set()

    for table in tables:
        table_spec = _require_mapping(table, "table")
        table_name = table_spec.get("name")
        if not table_name:
            raise SemanticValidationError("table missing name")
        if table_name in table_names:
            raise SemanticValidationError(f"Duplicate table name: {table_name}")
        table_names.add(table_name)

        base_table = _require_mapping(table_spec.get("base_table"), f"table {table_name} base_table")
        if not base_table.get("table"):
            raise SemanticValidationError(f"table {table_name} missing base_table.table")
        _validate_ai_context(table_spec.get("ai_context"), f"table {table_name}")

        build_table_alias(table_name, used_aliases)

        _validate_named_expr_objects(_require_list(table_spec.get("dimensions"), "dimensions"), "dimensions")
        _validate_named_expr_objects(
            _require_list(table_spec.get("time_dimensions"), "time_dimensions"),
            "time_dimensions",
        )
        _validate_named_expr_objects(_require_list(table_spec.get("facts"), "facts"), "facts")
        _validate_metrics(_require_list(table_spec.get("metrics"), "metrics"))

        table_object_names = set()
        for key in ("dimensions", "time_dimensions", "facts", "metrics"):
            for item in _require_list(table_spec.get(key), key):
                name = item["name"]
                if name in table_object_names:
                    raise SemanticValidationError(
                        f"Duplicate semantic object name in table {table_name}: {name}"
                    )
                table_object_names.add(name)

    for join in _require_list(spec.get("joins"), "joins"):
        join_spec = _require_mapping(join, "join")
        join_name = join_spec.get("name")
        if not join_name:
            raise SemanticValidationError("join missing name")
        left_table = join_spec.get("left_table")
        right_table = join_spec.get("right_table")
        if left_table not in table_names:
            raise SemanticValidationError(f"join {join_name} references unknown left_table: {left_table}")
        if right_table not in table_names:
            raise SemanticValidationError(f"join {join_name} references unknown right_table: {right_table}")
        if not join_spec.get("join_type"):
            raise SemanticValidationError(f"join {join_name} missing join_type")
        if not join_spec.get("join_expr"):
            raise SemanticValidationError(f"join {join_name} missing join_expr")
        _validate_ai_context(join_spec.get("ai_context"), f"join {join_name}")
