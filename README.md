# semduck

Semduck is a semantic view runtime for DuckDB. It lets you register semantic definitions, compile a compact request language into SQL, and use the same runtime from Python, the CLI, dbt, or an MCP server.

Full documentation lives in the GitHub Pages docs site built from [`docs/`](docs).

## Quickstart

```bash
pip install semduck

semduck init --db demo.duckdb
semduck load --db demo.duckdb --file orders_semantic.yaml
semduck query --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

## Packages

- [`packages/semduck`](packages/semduck): Python package with the runtime, CLI, compiler, registry, MCP server, ask workflow, and DuckDB plugin code
- [`packages/dbt-semduck`](packages/dbt-semduck): dbt package with macros and materializations for semantic view registration and query compilation

## Repo Layout

- [`docs`](docs): GitHub Pages documentation site
- [`examples/dbt_example`](examples/dbt_example): end-to-end `dbt-duckdb` example project
- [`integration_tests`](integration_tests): end-to-end dbt integration coverage
- [`examples/test_fixtures`](examples/test_fixtures): fixture projects used by automated tests

## Package Boundary

- `semduck` owns the runtime, compiler, registry, CLI, Python API, MCP server, and DuckDB plugin surface.
- `dbt-semduck` owns dbt-facing macros and materializations.
- dbt support uses inline semantic DDL rather than YAML-in-dbt.

## Development

```bash
uv sync
uv run pytest
```
