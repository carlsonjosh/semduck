from __future__ import annotations

from importlib.resources import files
from typing import Any


def init_registry_schema(conn: Any) -> None:
    ddl_path = files("duckdb_semantic.ddl").joinpath("registry.sql")
    conn.execute(ddl_path.read_text(encoding="utf-8"))

