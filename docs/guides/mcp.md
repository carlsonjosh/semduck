# MCP

Semduck can run as a FastMCP server over `stdio`.

If you are exposing Semduck to Codex Desktop or other MCP clients on an ongoing basis, read [MCP Best Practices](mcp-best-practices.md) alongside this page.

## Start The Server

Against the example database:

```bash
semduck mcp --db examples/dbt_example/jaffle_shop.duckdb
```

If you want the server to advertise default ask-model settings to clients, add an LLM config:

```bash
semduck mcp \
  --db examples/dbt_example/jaffle_shop.duckdb \
  --config packages/semduck/examples/ask_ollama_config.yaml
```

The repository also includes `packages/semduck/examples/mcp_server_stdio.sh`.

## Client Configuration

Generic JSON example:

```json
{
  "mcpServers": {
    "semduck": {
      "command": "uv",
      "args": [
        "run",
        "python",
        "-m",
        "semduck.cli",
        "mcp",
        "--db",
        "/absolute/path/to/semduck/examples/dbt_example/jaffle_shop.duckdb"
      ]
    }
  }
}
```

Reference file: `packages/semduck/examples/mcp_client_config.json`

## Exposed Interface

Tools:

- `init_registry`
- `check_definition`
- `load_definition`
- `compile_request`
- `query_request`
- `list_semantic_views`
- `describe_semantic_view`

Resources:

- `semduck://registry`
- `semduck://grammar`
- `semduck://views/{view_name}`

Prompts:

- `ask_semduck_question`
- `choose_semantic_view`
- `debug_failed_request`

## Recommended Client Workflow

1. Read `semduck://registry` or call `list_semantic_views`.
2. Inspect the likely view with `describe_semantic_view`.
3. Draft a semduck request, not raw SQL.
4. Call `compile_request`.
5. Only after compilation succeeds, call `query_request`.
