from __future__ import annotations

import os
import subprocess
from pathlib import Path

import duckdb


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = REPO_ROOT / "integration_tests" / "dbt_project"
SEMDUCK_SRC = REPO_ROOT / "packages" / "semduck" / "src"


def _run_dbt(args: list[str], *, env: dict[str, str]) -> None:
    subprocess.run(
        ["dbt", *args],
        cwd=PROJECT_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_dbt_semduck_end_to_end(tmp_path):
    db_path = tmp_path / "integration.duckdb"
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    profiles_dir.joinpath("profiles.yml").write_text(
        f"""
semduck_integration:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: {db_path}
      threads: 1
      module_paths:
        - {SEMDUCK_SRC}
      plugins:
        - module: semduck.dbt.plugin
""".strip()
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["DBT_PROFILES_DIR"] = str(profiles_dir)

    _run_dbt(["deps"], env=env)
    _run_dbt(["seed"], env=env)
    _run_dbt(["run"], env=env)

    conn = duckdb.connect(str(db_path))
    try:
        semantic_views = conn.sql(
            "select view_name from semantic.semantic_views order by view_name"
        ).fetchall()
        assert semantic_views == [("orders_semantic",), ("raw_orders_semantic",)]

        query_rows = conn.sql(
            "select region, total_revenue from query_orders order by region"
        ).fetchall()
        assert query_rows == [("CA", 200), ("US", 250)]

        source_relation = conn.sql(
            """
            select physical_schema, physical_table
            from semantic.semantic_view_tables
            where view_name = 'raw_orders_semantic'
            """
        ).fetchone()
        assert source_relation == ("main", "orders_seed")
    finally:
        conn.close()
