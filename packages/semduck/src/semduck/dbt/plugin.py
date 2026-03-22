from __future__ import annotations

import json
from typing import Any

from semduck.api import (
    check_semantic_spec,
    compile_request_sql,
    init_registry,
    load_semantic_ddl,
    load_semantic_spec,
)

try:
    from dbt.adapters.duckdb.plugins import BasePlugin
except ImportError:  # pragma: no cover - exercised in dbt integration tests when installed
    class BasePlugin:  # type: ignore[no-redef]
        def __init__(self, *_args, **_kwargs):
            pass


def _load_json_spec(spec_json: str) -> dict[str, Any]:
    spec = json.loads(spec_json)
    if not isinstance(spec, dict):
        raise TypeError("resolved semantic spec must be a JSON object")
    return spec


def _check_resolved_spec(spec_json: str) -> str:
    spec = _load_json_spec(spec_json)
    result = check_semantic_spec(None, spec)  # type: ignore[arg-type]
    return f"ok check view_name={result.view_name}"


def _load_resolved_spec(conn: Any, spec_json: str) -> str:
    spec = _load_json_spec(spec_json)
    result = load_semantic_spec(conn, spec)
    return f"ok load view_name={result.view_name}"


def _check_ddl(ddl_text: str) -> str:
    result = load_semantic_ddl(None, ddl_text, validate_only=True)  # type: ignore[arg-type]
    return f"ok check view_name={result.view_name}"


def _load_ddl(conn: Any, ddl_text: str) -> str:
    result = load_semantic_ddl(conn, ddl_text)
    return f"ok load view_name={result.view_name}"


def _compile(conn: Any, request: str) -> str:
    return compile_request_sql(conn, request)


def register_plugin_functions(conn: Any) -> None:
    conn.create_function(
        "semduck_check_resolved_spec",
        lambda spec_json: _check_resolved_spec(spec_json),
        [str],
        str,
    )
    conn.create_function(
        "semduck_load_resolved_spec",
        lambda spec_json: _load_resolved_spec(conn, spec_json),
        [str],
        str,
        side_effects=True,
    )
    conn.create_function(
        "semduck_check_ddl",
        lambda ddl_text: _check_ddl(ddl_text),
        [str],
        str,
    )
    conn.create_function(
        "semduck_load_ddl",
        lambda ddl_text: _load_ddl(conn, ddl_text),
        [str],
        str,
        side_effects=True,
    )
    conn.create_function(
        "semduck_compile",
        lambda request: _compile(conn, request),
        [str],
        str,
    )


class SemduckPlugin(BasePlugin):
    def configure_connection(self, conn: Any) -> None:
        init_registry(conn)
        register_plugin_functions(conn)


Plugin = SemduckPlugin
