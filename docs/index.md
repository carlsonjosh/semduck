# semduck

Semduck is a semantic layer for DuckDB built for local analytics.

It helps you define semantic views once, then reuse those definitions across people, scripts, apps, and agents. Instead of rebuilding the same joins and metrics in raw SQL every time, you ask for dimensions, metrics, and filters and let Semduck compile the query.

## The Problem

DuckDB makes local analysis fast. The hard part is keeping the meaning of the data consistent once more than one query, notebook, script, or tool is involved.

Typical failure modes:

- the same metric gets redefined in multiple places
- joins are copied by hand and drift over time
- analysts know the business question but still need to reconstruct the SQL
- machine clients can access the database, but not the semantic intent behind it

Semduck addresses that gap with semantic views stored in DuckDB and a small request language that works for both humans and machines.

## The Core Flow

1. Author a semantic view in YAML or semantic DDL.
2. Load it into the Semduck registry in DuckDB.
3. Ask for metrics, dimensions, and filters.
4. Compile to SQL or execute directly.

Example:

```bash
pip install semduck

semduck init --db demo.duckdb
semduck load --db demo.duckdb --file orders_semantic.yaml
semduck query --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

The request stays semantic. Semduck resolves the view definition, joins, and metric expressions for you.

## Where It Fits

- Python or CLI: local scripts, notebooks, and direct analysis workflows
- dbt: semantic views authored with inline DDL and queried from downstream models
- MCP: tool-friendly access for machine clients that need to inspect and query semantic views
- `ask`: natural-language analytics over the same semantic runtime

## Start Here

- [Installation](getting-started/installation.md)
- [Quickstart](getting-started/quickstart.md)
- [How Semduck Works](guides/how-semduck-works.md)
- [Choosing An Integration](guides/choosing-an-integration.md)
- [CLI Guide](guides/cli.md)
- [Python API Guide](guides/python-api.md)
- [dbt Guide](guides/dbt.md)
- [MCP Guide](guides/mcp.md)
