from __future__ import annotations

from pathlib import Path

import duckdb

from semduck import compile_request, init_registry, load_semantic_yaml_file


def main() -> None:
    example_dir = Path(__file__).resolve().parent
    conn = duckdb.connect(":memory:")
    conn.execute("create schema mart")
    conn.execute(
        """
        create table mart.orders_base (
            order_id integer,
            customer_id integer,
            region varchar,
            order_date date,
            revenue double
        )
        """
    )
    conn.execute(
        """
        insert into mart.orders_base values
            (1, 10, 'US', '2024-01-01', 100.0),
            (2, 11, 'US', '2024-01-02', 150.0),
            (3, 12, 'CA', '2024-01-03', 200.0)
        """
    )

    init_registry(conn)
    load_semantic_yaml_file(conn, str(example_dir / "orders_semantic.yaml"))
    compiled = compile_request(
        conn,
        "orders_semantic dimensions region metrics total_revenue where region = 'US'",
    )
    print(compiled.sql)


if __name__ == "__main__":
    main()
