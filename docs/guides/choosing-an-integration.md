# Choosing An Integration

Semduck currently supports four main usage patterns.

## Python And CLI

Choose this if you want the thinnest path:

- direct control over DuckDB connections
- YAML or DDL definitions
- explicit compile and execute steps
- local scripts, notebooks, or service integration

Start with the [Quickstart](../getting-started/quickstart.md), then read [CLI](cli.md) and [Python API](python-api.md).

## dbt

Choose this if your semantic definitions should live inside a `dbt-duckdb` project and be queried from downstream models.

Use:

- the DuckDB plugin from `semduck`
- macros and materializations from `dbt-semduck`
- inline semantic DDL through `semduck_semantic`

Read [dbt](dbt.md).

## MCP

Choose this if you want an MCP client to discover semantic views, compile requests, and execute them through a tool interface.

Use:

- `semduck mcp`
- FastMCP tools, resources, and prompts
- `stdio` transport for local client integration

Read [MCP](mcp.md).

## Ask

Choose this if users ask analytics questions in natural language and semduck should plan, compile, execute, and optionally summarize the result.

Use:

- `semduck ask`
- an LLM provider config
- optional task-specific planner and summary models

Read [Ask](ask.md).
