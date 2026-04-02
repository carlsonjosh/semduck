# Quickstart

This walkthrough uses the standalone Python package and CLI path. It assumes you already have a DuckDB database and a semantic definition file.

## 1. Initialize The Registry

Create the semduck registry schema in your target DuckDB database:

```bash
semduck init --db demo.duckdb
```

This creates the semantic schema and supporting registry tables that semduck reads from when compiling requests.

## 2. Load A Semantic Definition

YAML:

```bash
semduck load --db demo.duckdb --file orders_semantic.yaml
```

DDL:

```bash
semduck load --db demo.duckdb --format ddl --file orders_semantic.sql
```

The CLI supports `--format auto|yaml|ddl`. In `auto` mode, semduck infers the format from the file extension or the first non-empty line.

## 3. Compile Or Execute A Request

Compile to SQL:

```bash
semduck compile --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

Execute directly:

```bash
semduck query --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

## 4. Equivalent Python API

```python
import duckdb
from semduck import compile_request_sql, init_registry, load_semantic_yaml_file

conn = duckdb.connect("demo.duckdb")
init_registry(conn)
load_semantic_yaml_file(conn, "orders_semantic.yaml")

sql = compile_request_sql(
    conn,
    "orders_semantic dimensions region metrics total_revenue",
)
print(sql)
```

## 5. Use The Example Project

The repository includes a working dbt-backed example database in `examples/dbt_example`.

- Standalone Python example: `packages/semduck/examples/query_existing_db.py`
- CLI wrapper: `packages/semduck/examples/query_existing_db_cli.sh`
- End-to-end dbt project: `examples/dbt_example`

## Next Steps

- Learn the [request language](../guides/request-language.md).
- Choose between [YAML and DDL definitions](../guides/semantic-definitions.md).
- Move to [dbt](../guides/dbt.md), [MCP](../guides/mcp.md), or [ask](../guides/ask.md) if you need those integrations.
