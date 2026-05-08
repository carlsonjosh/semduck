from __future__ import annotations

import os
from uuid import uuid4

import pytest

from semduck import execute_request, init_registry, load_semantic_yaml
from semduck.connections import connect_database


def _motherduck_database() -> str:
    database = os.environ.get("MOTHERDUCK_TEST_DATABASE")
    token = os.environ.get("MOTHERDUCK_TOKEN") or os.environ.get("motherduck_token")
    if not database or not token:
        pytest.skip(
            "MotherDuck integration test requires MOTHERDUCK_TEST_DATABASE and MOTHERDUCK_TOKEN."
        )
    return database
def test_weather_quickstart_query_on_motherduck(weather_yaml_path):
    database = _motherduck_database()
    table_name = f"weather_raw_{uuid4().hex[:8]}"
    view_name = f"weather_{uuid4().hex[:8]}"

    conn = connect_database(database)
    try:
        init_registry(conn)
        conn.execute(
            f"""
            create or replace table {table_name} as
            select *
            from (
                values
                    (DATE '2024-01-01', 'Seattle', 'rain', 5.0, 48.0, 38.0, 8.0),
                    (DATE '2024-01-02', 'Seattle', 'sun', 0.0, 50.0, 36.0, 5.0),
                    (DATE '2024-01-01', 'New York', 'fog', 1.0, 42.0, 30.0, 10.0),
                    (DATE '2024-01-02', 'New York', 'rain', 3.0, 44.0, 32.0, 12.0)
            ) as weather_raw(date, location, weather, precipitation, temp_max, temp_min, wind)
            """
        )

        yaml_text = weather_yaml_path.read_text(encoding="utf-8")
        yaml_text = yaml_text.replace("name: weather\n", f"name: {view_name}\n", 1)
        yaml_text = yaml_text.replace("table: weather_raw", f"table: {table_name}")
        load_semantic_yaml(conn, yaml_text)

        result = execute_request(
            conn,
            f"{view_name} dimensions location, weather metrics day_count, avg_temp_max",
        )
        rows = sorted(result.fetchall())
    finally:
        conn.execute(f"drop table if exists {table_name}")
        conn.close()

    assert rows == [
        ("New York", "fog", 1, 42.0),
        ("New York", "rain", 1, 44.0),
        ("Seattle", "rain", 1, 48.0),
        ("Seattle", "sun", 1, 50.0),
    ]
