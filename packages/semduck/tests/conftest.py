from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from semduck import init_registry, load_semantic_yaml_file


@pytest.fixture
def conn():
    connection = duckdb.connect(":memory:")
    init_registry(connection)
    yield connection
    connection.close()


@pytest.fixture
def orders_yaml_path() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "orders_semantic.yaml"


@pytest.fixture
def loaded_conn(conn, orders_yaml_path):
    conn.execute("create schema mart")
    conn.execute(
        """
        create table mart.orders_base (
            order_id integer,
            customer_id integer,
            region varchar,
            order_date date,
            revenue double,
            unit_costs double
        )
        """
    )
    conn.execute(
        """
        create table mart.customers_base (
            customer_id integer,
            customer_segment varchar
        )
        """
    )
    conn.execute(
        """
        insert into mart.orders_base values
            (1, 10, 'US', '2024-01-01', 100.0, 60.0),
            (2, 11, 'US', '2024-01-02', 150.0, 90.0),
            (3, 12, 'CA', '2024-01-03', 200.0, 120.0)
        """
    )
    conn.execute(
        """
        insert into mart.customers_base values
            (10, 'Enterprise'),
            (11, 'SMB'),
            (12, 'Consumer')
        """
    )
    load_semantic_yaml_file(conn, str(orders_yaml_path))
    return conn


@pytest.fixture
def ecommerce_registry_conn(conn):
    examples_dir = Path(__file__).resolve().parents[3] / "examples" / "ecommerce"
    for filename in ("orders_semantic.yaml", "customer_semantic.yaml", "product_sales_semantic.yaml"):
        load_semantic_yaml_file(conn, str(examples_dir / filename))
    return conn
