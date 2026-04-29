# Installation

## Python Package

Install the core package:

```bash
pip install semduck
```

If you prefer `uv`, use:

```bash
uv add semduck
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

With `uv`:

```bash
uv add "semduck[dbt]"
```

The dbt-facing macros and materializations live in the separate `dbt-semduck` package in this repository.

## Python Version

The packaged project currently targets Python `>=3.11,<3.14`.

## What To Read Next

- For the smallest standalone path, go to [Quickstart](quickstart.md).
- If you need the dbt interface, go to [dbt](../interfaces/dbt.md).
- If you want the MCP interface for AI tooling, go to [MCP](../interfaces/mcp.md).
- If you want natural-language analytics, go to [Ask](../interfaces/ask.md).
