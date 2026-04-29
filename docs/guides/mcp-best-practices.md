# MCP Best Practices

This guide is for teams who want to expose one or more Semduck-backed DuckDB databases to MCP clients such as Codex Desktop.

The main goal is simple: make the semantic layer the default source of truth for analytics questions, while keeping server selection obvious when multiple databases are available.

## Design For Clear Routing

If you expose more than one Semduck MCP server, do not make clients guess which one to use.

Recommended pattern:

- run one Semduck MCP server per DuckDB database or per clearly defined environment
- use descriptive server names such as `semduck-sales-prod`, `semduck-growth-dev`, or `semduck-jaffle-local`
- avoid generic names such as `semduck` when multiple servers are configured
- keep each server scoped to one business domain or one environment when possible

This gives agents and users a stable way to choose the right endpoint before any query runs.

## Make Servers Query-Ready

Users should not need to remember setup steps after the server starts.

Recommended pattern:

- initialize the Semduck registry in the target DuckDB file before users connect
- load the semantic definitions needed for that database ahead of time
- keep view names stable across sessions
- keep the backing DuckDB path stable for a named server

If the server starts against an empty registry, agents may need to load definitions before they can answer anything. That is workable, but it is not a good default for shared usage.

## Keep Semantic Names Stable

The more semantic requests look like business language, the more naturally agents can use Semduck first.

Recommended pattern:

- choose view names that reflect the business object, such as `orders`, `customers`, or `finance_pnl`
- choose dimension and metric names that match how users already talk
- avoid multiple near-synonyms for the same concept across different databases
- preserve the same metric names across environments when the definition is meant to be the same

This matters more than it seems. When names drift, agents fall back to inspection and clarification more often.

## Prefer One Server Per Environment

Do not overload a single server with too many meanings.

A simple layout works best:

- one local or personal analysis server
- one shared dev server
- one shared prod server

For example:

- `semduck-sales-local`
- `semduck-sales-dev`
- `semduck-sales-prod`

That pattern makes it obvious when a question should hit local experimentation versus a production-grade semantic catalog.

## Tell Users How To Configure Clients

Users need both server configuration and standing instructions.

For Codex Desktop, Claude Desktop or other MCP clients, recommend:

1. Register each Semduck MCP server separately.
2. Use names that encode domain and environment.
3. Keep those names consistent with the DuckDB database they represent.

Example:

```json
{
  "mcpServers": {
    "semduck-sales-prod": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "semduck.cli",
        "mcp",
        "--db",
        "/absolute/path/to/sales_prod.duckdb"
      ]
    },
    "semduck-growth-dev": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "semduck.cli",
        "mcp",
        "--db",
        "/absolute/path/to/growth_dev.duckdb"
      ]
    }
  }
}
```

## Give The Agent A Standing Rule

The client should be told to prefer Semduck over inference, docs, or source inspection when a Semduck server can answer directly.

Recommended standing instruction:

```text
Use Semduck MCP servers as the default source of truth for analytics questions.
If a Semduck server is available, query it before using docs, source code, or inference.
If multiple Semduck servers are configured, inspect their metadata and choose the best match.
If the choice is still ambiguous, ask which server to use.
Always state which Semduck server and semantic view answered the question.
```

That instruction is short enough to be practical to include in system instructions and specific enough to change behavior.

## Recommended Agent Workflow

When the user does not name a server or view explicitly, the safest workflow is:

1. Identify the most likely Semduck server from the configured server names.
2. Inspect available views with `list_semantic_views`.
3. Inspect the likely view with `describe_semantic_view`.
4. Compile the semantic request with `compile_request`.
5. Execute it with `query_request`.
6. Report the server and view used in the answer.

If multiple servers are plausible after inspection, the agent should ask instead of guessing.

## What To Tell End Users

Users do not need a long setup guide. They need a few rules that keep questions unambiguous.

Tell them to:

- name the environment when it matters, such as "sales prod" or "local jaffle"
- refer to business metrics and dimensions by their semantic names
- expect the agent to confirm the server or view when multiple choices exist
- treat Semduck as the analytics source of truth when a Semduck server is configured

## What Semduck Can Do Better

Some of the user experience depends on the MCP client, but Semduck itself can make multi-server usage feel much more natural.

The most helpful improvements are:

- a `server_info` or `describe_connection` tool that reports server identity, database path, environment, and purpose
- richer `list_semantic_views` output with descriptions, tags, and domain metadata
- clearer environment labeling for shared deployments
- view-level metadata such as owner, grain, and business description

Those additions make routing and trust much easier for both users and agents.

## Checklist

For teams rolling this out broadly:

- give every server a clear domain-and-environment name
- preload the registry and definitions before users connect
- keep semantic names stable across environments
- add standing client instructions that prefer Semduck first
- tell agents to report the server and view used
- avoid forcing clients to guess between multiple plausible servers
