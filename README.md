# duckdb-semantic

Portable semantic view runtime for DuckDB, implemented in Python.

## Quickstart

```bash
uv sync
uv run duckdb-semantic init-registry --db demo.duckdb
uv run duckdb-semantic load-yaml --db demo.duckdb --file examples/orders_semantic.yaml
uv run duckdb-semantic compile --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

## Development

```bash
uv sync
uv run pytest
```

