from __future__ import annotations

from typing import Any

import duckdb


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _motherduck_database_name(path: str) -> str | None:
    if not path.startswith("md:"):
        return None

    database_name = path.removeprefix("md:")
    if not database_name:
        return None

    return database_name


def connect_database(path: str) -> Any:
    database_name = _motherduck_database_name(path)
    if database_name is not None:
        control_conn = duckdb.connect("md:")
        try:
            control_conn.execute(
                f"create database if not exists {_quote_identifier(database_name)}"
            )
        finally:
            control_conn.close()

    return duckdb.connect(path)
