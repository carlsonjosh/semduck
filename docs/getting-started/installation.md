# Installation

## Python Package

Install the core package:

```bash
pip install semduck
```

This gives you:

- the Python API
- the `semduck` CLI
- YAML and DDL loading
- request compilation and execution
- the MCP server
- the `ask` workflow

## Optional dbt Support

Install the dbt extra only if you are registering the DuckDB plugin inside a `dbt-duckdb` project:

```bash
pip install "semduck[dbt]"
```

The dbt-facing macros and materializations live in the separate `dbt-semduck` package in this repository.

## Python Version

The packaged project currently targets Python `>=3.11,<3.13`.

## Local Development

From the repository root:

```bash
uv sync
uv run pytest
```

## What To Read Next

- For the smallest standalone path, go to [Quickstart](quickstart.md).
- If you need dbt integration, go to [dbt](../guides/dbt.md).
- If you want an MCP server for AI tooling, go to [MCP](../guides/mcp.md).
- If you want natural-language analytics, go to [Ask](../guides/ask.md).
