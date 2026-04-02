# semduck

Semantic views for DuckDB.

Semduck is for people doing serious analysis on their local machine with DuckDB who are tired of rebuilding the same joins, metrics, and business logic in raw SQL. It lets you define semantic views once, then query them consistently from Python, the CLI, dbt, MCP clients, or an `ask` workflow.

Humans can use it. Machines can use it. Both get the same semantic contract.

## Why It Matters

DuckDB is fast. Recreating analytics logic is not.

Without a semantic layer, every useful question turns into hand-written SQL:

- metrics get redefined across notebooks and scripts
- joins get copied, edited, and broken
- analysts know the question but still have to reconstruct the query
- agents and apps can reach the database, but not the meaning of the data

Semduck fixes that by storing semantic views in DuckDB and compiling semantic requests into SQL.

## What You Do With It

- Define metrics, dimensions, and joins once
- Query those definitions with a compact request language
- Reuse the same runtime from local scripts, notebooks, tools, and agents
- Expose DuckDB analysis to humans and machines without making raw SQL the interface

## Quick Example

```bash
pip install semduck

semduck init --db demo.duckdb
semduck load --db demo.duckdb --file orders_semantic.yaml
semduck query --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

Instead of writing SQL, you ask for the business objects you care about. Semduck resolves the view, joins, and metric definitions for you.

## What A Semantic View Looks Like

```yaml
name: orders_semantic
tables:
  - name: orders
    base_table:
      table: orders
    dimensions:
      - name: region
        expr: region
    metrics:
      - name: total_revenue
        metric_type: sum
        expr: revenue
```

## How It Works

1. Define a semantic view in YAML or semantic DDL.
2. Load it into a registry stored in DuckDB.
3. Query it with dimensions, metrics, and filters.
4. Compile to SQL or execute directly.

The same runtime powers:

- Python and CLI workflows
- dbt projects through `dbt-semduck`
- MCP clients that need a tool-friendly analytics surface
- `semduck ask` for natural-language analytics flows

## Start Here

- [Quickstart](docs/getting-started/quickstart.md)
- [How Semduck Works](docs/guides/how-semduck-works.md)
- [Choosing An Integration](docs/guides/choosing-an-integration.md)
- [Package README](packages/semduck)
- [Docs Site Source](docs)

## Packages

- [`packages/semduck`](packages/semduck): Python runtime, CLI, compiler, registry, MCP server, ask workflow, and DuckDB integration
- [`packages/dbt-semduck`](packages/dbt-semduck): dbt macros and materializations for semantic view registration and query compilation

## Repo Layout

- [`docs`](docs): GitHub Pages documentation site
- [`examples/dbt_example`](examples/dbt_example): end-to-end `dbt-duckdb` example project
- [`integration_tests`](integration_tests): end-to-end dbt integration coverage
- [`examples/test_fixtures`](examples/test_fixtures): fixture projects used by automated tests

## Development

```bash
uv sync
uv run pytest
uv run tox
```

## Compatibility Baseline

- Python: `3.11` through `3.13`
- DuckDB: `1.4+`
- dbt integration: `dbt-duckdb` `1.10.x` or newer within the supported range
