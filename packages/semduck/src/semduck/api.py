from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from semduck.authoring.ddl_loader import load_ddl_spec
from semduck.authoring.validators import validate_semantic_spec
from semduck.authoring.yaml_loader import load_yaml_spec
from semduck.errors import SemanticValidationError
from semduck.parser.request_parser import parse_request as parse_semantic_request
from semduck.registry.reader import load_semantic_view_registry
from semduck.registry.schema import init_registry_schema
from semduck.registry.writer import write_semantic_view
from semduck.runtime.executor import compile_semantic_request, execute_semantic_request
from semduck.types import CompiledSemanticQuery, LoadResult, ParsedSemanticRequest, SemanticViewRegistry


def _merge_unique_strings(existing: list[Any], overlay: list[Any]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in list(existing) + list(overlay):
        if not isinstance(item, str):
            continue
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return merged


def _merge_ai_context(
    existing: dict[str, Any] | None,
    overlay: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if existing is None:
        return deepcopy(overlay) if overlay is not None else None
    if overlay is None:
        return existing
    merged: dict[str, Any] = deepcopy(existing)
    for key, overlay_value in overlay.items():
        if key not in merged:
            merged[key] = deepcopy(overlay_value)
            continue
        existing_value = merged[key]
        if key == "concepts" and isinstance(existing_value, list) and isinstance(overlay_value, list):
            merged[key] = _merge_ai_context_concepts(existing_value, overlay_value)
            continue
        if key == "phrases" and isinstance(existing_value, list) and isinstance(overlay_value, list):
            merged[key] = _merge_unique_strings(existing_value, overlay_value)
            continue
        if isinstance(existing_value, dict) and isinstance(overlay_value, dict):
            merged[key] = _merge_ai_context(existing_value, overlay_value)
            continue
        merged[key] = deepcopy(overlay_value)
    return merged


def _merge_ai_context_concepts(
    existing: list[Any],
    overlay: list[Any],
) -> list[Any]:
    merged = deepcopy(existing)
    concept_positions = {
        concept.get("concept_id"): index
        for index, concept in enumerate(merged)
        if isinstance(concept, dict) and isinstance(concept.get("concept_id"), str)
    }
    for overlay_concept in overlay:
        if not isinstance(overlay_concept, dict):
            merged.append(deepcopy(overlay_concept))
            continue
        concept_id = overlay_concept.get("concept_id")
        if not isinstance(concept_id, str) or concept_id not in concept_positions:
            merged.append(deepcopy(overlay_concept))
            continue
        existing_index = concept_positions[concept_id]
        existing_concept = merged[existing_index]
        if isinstance(existing_concept, dict):
            existing_kind = existing_concept.get("concept_kind")
            overlay_kind = overlay_concept.get("concept_kind")
            if (
                isinstance(existing_kind, str)
                and isinstance(overlay_kind, str)
                and existing_kind.strip()
                and overlay_kind.strip()
                and existing_kind != overlay_kind
            ):
                raise SemanticValidationError(
                    f"Conflicting concept_kind values for ai_context concept '{concept_id}': "
                    f"{existing_kind!r} vs {overlay_kind!r}"
                )
            merged[existing_index] = _merge_ai_context(existing_concept, overlay_concept)
    return merged


def _iter_semantic_objects(spec: dict[str, Any]) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for table in spec.get("tables", []):
        if not isinstance(table, dict):
            continue
        for section in ("dimensions", "time_dimensions", "facts", "metrics"):
            for obj in table.get(section, []) or []:
                if isinstance(obj, dict):
                    objects.append(obj)
    return objects


def _apply_dbt_metadata_overlay(
    spec: dict[str, Any],
    dbt_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    if not dbt_metadata:
        return spec

    model_meta = dbt_metadata.get("meta")
    config_meta = dbt_metadata.get("config_meta")
    model_ai_context = None
    if isinstance(config_meta, dict):
        model_ai_context = config_meta.get("ai_context")
    if isinstance(model_meta, dict):
        model_ai_context = _merge_ai_context(model_ai_context, model_meta.get("ai_context"))
    if isinstance(model_ai_context, dict):
        spec["ai_context"] = _merge_ai_context(spec.get("ai_context"), model_ai_context)

    object_matches: dict[str, list[dict[str, Any]]] = {}
    for obj in _iter_semantic_objects(spec):
        name = obj.get("name")
        if isinstance(name, str):
            object_matches.setdefault(name, []).append(obj)

    columns = dbt_metadata.get("columns")
    if not isinstance(columns, dict):
        return spec

    for column_name, column_payload in columns.items():
        if not isinstance(column_name, str) or not isinstance(column_payload, dict):
            continue
        column_meta = column_payload.get("meta")
        if not isinstance(column_meta, dict):
            continue
        column_ai_context = column_meta.get("ai_context")
        if not isinstance(column_ai_context, dict):
            continue
        matches = object_matches.get(column_name, [])
        if not matches:
            raise SemanticValidationError(
                f"dbt column meta.ai_context for '{column_name}' does not match any semantic object in the DDL"
            )
        if len(matches) > 1:
            raise SemanticValidationError(
                f"dbt column meta.ai_context for '{column_name}' is ambiguous across multiple semantic objects"
            )
        matches[0]["ai_context"] = _merge_ai_context(matches[0].get("ai_context"), column_ai_context)

    return spec


def init_registry(conn: Any) -> None:
    init_registry_schema(conn)


def load_semantic_spec(
    conn: Any,
    spec: dict[str, Any],
    *,
    replace_existing: bool = True,
    validate_only: bool = False,
    source_yaml: str | None = None,
) -> LoadResult:
    validate_semantic_spec(spec)
    source = source_yaml or json.dumps(spec, sort_keys=True)
    result = write_semantic_view(
        conn,
        spec,
        source_yaml=source,
        replace_existing=replace_existing,
        validate_only=validate_only,
    )
    if conn is not None and not validate_only:
        # Keep the derived concept index in sync with registry loads so dbt build
        # and direct DDL/YAML loads populate semantic.semantic_concept_* eagerly.
        from semduck.agent.validation.concept_store import ensure_semantic_concepts
        from semduck.agent.validation.policy import DEFAULT_VALIDATION_POLICY

        ensure_semantic_concepts(conn, DEFAULT_VALIDATION_POLICY)
    return result


def check_semantic_spec(conn: Any, spec: dict[str, Any]) -> LoadResult:
    return load_semantic_spec(conn, spec, validate_only=True)


def load_semantic_yaml(
    conn: Any,
    yaml_text: str,
    *,
    replace_existing: bool = True,
    validate_only: bool = False,
) -> LoadResult:
    spec = load_yaml_spec(yaml_text)
    return load_semantic_spec(
        conn,
        spec,
        replace_existing=replace_existing,
        validate_only=validate_only,
        source_yaml=yaml_text,
    )


def load_semantic_ddl(
    conn: Any,
    ddl_text: str,
    *,
    replace_existing: bool = True,
    validate_only: bool = False,
    dbt_metadata: dict[str, Any] | None = None,
) -> LoadResult:
    spec = load_ddl_spec(ddl_text)
    spec = _apply_dbt_metadata_overlay(spec, dbt_metadata)
    return load_semantic_spec(
        conn,
        spec,
        replace_existing=replace_existing,
        validate_only=validate_only,
        source_yaml=ddl_text,
    )


def load_semantic_yaml_file(
    conn: Any,
    path: str,
    *,
    replace_existing: bool = True,
    validate_only: bool = False,
) -> LoadResult:
    yaml_text = Path(path).read_text(encoding="utf-8")
    return load_semantic_yaml(
        conn,
        yaml_text,
        replace_existing=replace_existing,
        validate_only=validate_only,
    )


def load_semantic_ddl_file(
    conn: Any,
    path: str,
    *,
    replace_existing: bool = True,
    validate_only: bool = False,
) -> LoadResult:
    ddl_text = Path(path).read_text(encoding="utf-8")
    return load_semantic_ddl(
        conn,
        ddl_text,
        replace_existing=replace_existing,
        validate_only=validate_only,
    )


def parse_request(request: str) -> ParsedSemanticRequest:
    return parse_semantic_request(request)


def get_semantic_view(conn: Any, view_name: str) -> SemanticViewRegistry:
    return load_semantic_view_registry(conn, view_name)


def list_semantic_views(conn: Any) -> list[str]:
    rows = conn.execute(
        """
        select view_name
        from semantic.semantic_views
        order by view_name
        """
    ).fetchall()
    return [row[0] for row in rows]


def compile_request(conn: Any, request: str) -> CompiledSemanticQuery:
    return compile_semantic_request(conn, request)


def execute_request(conn: Any, request: str):
    return execute_semantic_request(conn, request)


def compile_request_sql(conn: Any, request: str) -> str:
    return compile_request(conn, request).sql


def register_connection(conn: Any) -> None:
    from semduck.dbt.plugin import register_plugin_functions

    init_registry(conn)
    register_plugin_functions(conn)
