# CLI

The `semduck` CLI exposes the runtime, validation, query, ask, and MCP workflows.

## Commands

### `init`

Initialize the registry schema:

```bash
semduck init --db demo.duckdb
```

### `check`

Validate a semantic definition file without writing it:

```bash
semduck check --db demo.duckdb --file orders_semantic.yaml
semduck check --db demo.duckdb --format ddl --file orders_semantic.sql
```

### `load`

Load a semantic definition into the registry:

```bash
semduck load --db demo.duckdb --file orders_semantic.yaml
semduck load --db demo.duckdb --format ddl --file orders_semantic.sql
```

Use `--no-replace` to reject loading when the view already exists.

### `compile`

Compile a semantic request to SQL:

```bash
semduck compile --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

### `query`

Execute a semantic request and print a simple tabular result:

```bash
semduck query --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

### `ask`

Turn a natural-language analytics question into a semantic request, execute it, and optionally return SQL, tables, CSV, or a summary:

```bash
semduck ask \
  --db examples/dbt_example/jaffle_shop.duckdb \
  --config packages/semduck/examples/ask_ollama_config.yaml \
  --question "What is total revenue by customer name?" \
  --table --summary
```

Useful flags:

- `--config`, `--provider`, `--model` to choose an LLM provider
- `--view` to force a semantic view
- `--row-limit` to cap returned rows
- `--sql`, `--table`, `--csv`, `--summary` to choose outputs
- `--llm-log-dir` and `--no-llm-log` to control trace logging
- `--output-format text|json` for machine-readable output

During `ask`, semduck writes stage updates to `stderr` and final output to `stdout`.

### `mcp`

Start the MCP server over `stdio`:

```bash
semduck mcp --db examples/dbt_example/jaffle_shop.duckdb
```

Add `--config`, `--provider`, or `--model` if you want the server to expose default ask-model settings to connected clients.

## Format Detection

`check` and `load` support `--format auto|yaml|ddl`.

In `auto` mode semduck checks:

1. file extension
2. the first non-empty line for `create semantic view`

If neither indicates DDL, semduck treats the file as YAML.
