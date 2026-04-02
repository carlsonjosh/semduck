# semduck MCP Example

This example starts the semduck FastMCP server over `stdio` against the checked-in example
database at `examples/dbt_example/jaffle_shop.duckdb`.

## Start The Server

From the repo root:

```bash
uv run python -m semduck.cli mcp \
  --db examples/dbt_example/jaffle_shop.duckdb
```

If you want the server to advertise default ask-model settings to the client prompts and resources,
pass an LLM config as well:

```bash
uv run python -m semduck.cli mcp \
  --db examples/dbt_example/jaffle_shop.duckdb \
  --config packages/semduck/examples/ask_ollama_config.yaml
```

You can also use the wrapper script:

```bash
bash packages/semduck/examples/mcp_server_stdio.sh
```

Or with config:

```bash
bash packages/semduck/examples/mcp_server_stdio.sh \
  packages/semduck/examples/ask_ollama_config.yaml
```

## Connect From An MCP Client

Use a standard `stdio` MCP server entry in your client configuration.

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

If your client supports per-server environment variables or you want to expose ask defaults to the
client prompts, include `--config` as well:

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
        "/absolute/path/to/semduck/examples/dbt_example/jaffle_shop.duckdb",
        "--config",
        "/absolute/path/to/semduck/packages/semduck/examples/ask_ollama_config.yaml"
      ]
    }
  }
}
```

An example config file with both variants is included at
`packages/semduck/examples/mcp_client_config.json`.

## How A Client Should Use semduck MCP

The server exposes:

- tools:
  - `list_semantic_views`
  - `describe_semantic_view`
  - `compile_request`
  - `query_request`
  - `check_definition`
  - `load_definition`
  - `init_registry`
- resources:
  - `semduck://registry`
  - `semduck://grammar`
  - `semduck://views/{view_name}`
- prompts:
  - `ask_semduck_question`
  - `choose_semantic_view`
  - `debug_failed_request`

Recommended client workflow:

1. Read `semduck://registry` or call `list_semantic_views`.
2. Read `semduck://views/{view_name}` or call `describe_semantic_view`.
3. Generate a semduck request, not raw SQL.
4. Call `compile_request`.
5. If compilation succeeds, call `query_request`.
6. Return the answer with the semantic request and compiled SQL.
