from __future__ import annotations

from types import SimpleNamespace

from semduck.connections import connect_database


def test_connect_database_creates_motherduck_database_before_connect(monkeypatch):
    calls: list[str] = []
    executed_sql: list[str] = []

    def fake_connect(path: str):
        calls.append(path)

        def execute(sql: str):
            executed_sql.append(sql)
            return SimpleNamespace()

        return SimpleNamespace(execute=execute, close=lambda: None)

    monkeypatch.setattr("semduck.connections.duckdb.connect", fake_connect)

    connect_database("md:semduck_weather")

    assert calls == ["md:", "md:semduck_weather"]
    assert executed_sql == ['create database if not exists "semduck_weather"']


def test_connect_database_does_not_create_non_motherduck_database(monkeypatch):
    calls: list[str] = []

    def fake_connect(path: str):
        calls.append(path)
        return SimpleNamespace(close=lambda: None)

    monkeypatch.setattr("semduck.connections.duckdb.connect", fake_connect)

    connect_database(":memory:")

    assert calls == [":memory:"]
