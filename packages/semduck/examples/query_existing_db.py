from __future__ import annotations

from pathlib import Path

import duckdb

from semduck import compile_request, execute_request


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    db_path = repo_root / "examples" / "dbt_example" / "jaffle_shop.duckdb"
    request = "orders dimensions customer_name metrics total_revenue"

    conn = duckdb.connect(str(db_path), read_only=True)
    compiled = compile_request(conn, request)
    result = execute_request(conn, request)
    columns = [column[0] for column in result.description]
    rows = result.fetchall()

    print(f"Connected to: {db_path}")
    print(f"Request: {request}")
    print("Compiled SQL:")
    print(compiled.sql)
    print("\nResults:")
    print(columns)
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
