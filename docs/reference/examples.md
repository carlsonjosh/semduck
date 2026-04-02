# Examples

The repository already includes several runnable examples. This page is the index for them.

## Standalone Python And CLI

- `packages/semduck/examples/quickstart.py`: in-memory Python quickstart that creates a table, loads YAML, and compiles a request.
- `packages/semduck/examples/query_existing_db.py`: compile and execute a request against the checked-in example database.
- `packages/semduck/examples/query_existing_db_cli.sh`: CLI wrapper around the same example database.

## Ask

- `packages/semduck/examples/ask_existing_db_cli.sh`: run `semduck ask` against the example database.
- `packages/semduck/examples/ask_ollama_config.yaml`: example Ollama configuration.
- `packages/semduck/examples/ask_openai_compatible_config.yaml`: example OpenAI-compatible configuration.

## MCP

- `packages/semduck/examples/mcp_server_stdio.sh`: start the MCP server over `stdio`.
- `packages/semduck/examples/mcp_client_config.json`: example client configuration.
- `packages/semduck/examples/mcp_connection_guide.md`: lower-level MCP setup notes.

## dbt

- `examples/dbt_example`: end-to-end `dbt-duckdb` project using `dbt-semduck`.
- `examples/dbt_example/models/sev_orders.sql`: semantic registration model.
- `examples/dbt_example/models/rpt_customer_revenue.sql`: downstream `from_query(...)` example.
- `examples/dbt_example/models/rpt_customer_revenue_wrapped.sql`: downstream `query(...)` example.

## Fixtures And Integration Coverage

- `examples/test_fixtures/dbt_project`: source fixtures for automated integration tests.
- `integration_tests/test_dbt_semduck_integration.py`: end-to-end dbt integration test coverage.
