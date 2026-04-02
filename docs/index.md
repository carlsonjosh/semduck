# semduck

`semduck` is a semantic view runtime for DuckDB. It gives you a small semantic layer that can be loaded from YAML or semantic DDL, compiled from a compact request language into SQL, and used from Python, the CLI, dbt, or an MCP server.

## Start Here

Choose the path that matches how you want to use it:

- Python or CLI: install `semduck`, initialize a registry, load a definition, compile or execute requests.
- dbt: use `dbt-semduck` plus the DuckDB plugin to register semantic views from inline DDL and query them from downstream models.
- MCP: run the FastMCP server over `stdio` so an MCP client can inspect views, compile requests, and execute queries.
- `ask`: configure an LLM provider and let semduck turn natural-language analytics questions into semantic requests.

## Quick Example

```bash
pip install semduck

semduck init --db demo.duckdb
semduck load --db demo.duckdb --file orders_semantic.yaml
semduck query --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

The request language stays semantic. You ask for dimensions, metrics, and optional filters; semduck resolves joins and generates SQL against the registered semantic view.

## Core Concepts

- Registry: semduck stores semantic view definitions in a DuckDB schema.
- Definition: a semantic view can be authored in YAML or semantic DDL.
- Request: users query a view with a compact semantic request language, not raw SQL.
- Compiler: semduck resolves the request into executable SQL.
- Runtime: the compiled SQL can be returned, executed, or exposed through dbt and MCP integrations.

## Recommended Reading

- [Installation](getting-started/installation.md)
- [Quickstart](getting-started/quickstart.md)
- [How Semduck Works](guides/how-semduck-works.md)
- [Choosing An Integration](guides/choosing-an-integration.md)
- [CLI Guide](guides/cli.md)
- [Python API Guide](guides/python-api.md)
- [dbt Guide](guides/dbt.md)
- [MCP Guide](guides/mcp.md)
