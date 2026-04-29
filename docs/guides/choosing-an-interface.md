# Choosing An Interface

Semduck currently supports four main interfaces:

- Python API
- CLI
- dbt
- MCP

## Python or CLI

Choose one of these if you want the thinnest path:

- direct control over DuckDB connections
- YAML or DDL definitions
- explicit compile and execute steps
- local scripts, notebooks, or service workflows

Start with the [Quickstart](../getting-started/quickstart.md), then read [CLI](../interfaces/cli.md) and [Python API](../interfaces/python-api.md).

If you want a lighter-weight natural-language entry point without moving to MCP, the CLI also includes `semduck ask`.

Choose `semduck ask` when:

- you want to start from a business question instead of a semantic request
- you still want the local CLI workflow
- you want Semduck to plan, compile, execute, and optionally summarize the result

Use:

- `semduck ask`
- an LLM provider config
- optional task-specific planner and summary models

Read more at [Ask](../interfaces/ask.md).

## dbt

Choose this if your semantic definitions should live inside a `dbt-duckdb` project and be queried from downstream models.

Use:

- the DuckDB plugin from `semduck`
- macros and materializations from `dbt-semduck`
- inline semantic DDL through `semduck_semantic`

Read [dbt](../interfaces/dbt.md).

## MCP

Choose this if you want an MCP client to discover semantic views, compile requests, and execute them through a tool interface.

Use:

- `semduck mcp`
- FastMCP tools, resources, and prompts
- `stdio` transport for local client workflows

Read [MCP](../interfaces/mcp.md). Learn about [MCP Best Practices](mcp-best-practices.md).
