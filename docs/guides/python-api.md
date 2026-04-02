# Python API

The documented Python surface is intentionally small. Start with the functions in `semduck.api`.

## Registry And Loading

```python
import duckdb
from semduck import init_registry, load_semantic_yaml_file

conn = duckdb.connect("demo.duckdb")
init_registry(conn)
load_semantic_yaml_file(conn, "orders_semantic.yaml")
```

Core loaders:

- `init_registry(conn)`
- `load_semantic_yaml(conn, yaml_text)`
- `load_semantic_yaml_file(conn, path)`
- `load_semantic_ddl(conn, ddl_text)`
- `load_semantic_ddl_file(conn, path)`

## Compile And Execute

```python
from semduck import compile_request, compile_request_sql, execute_request

request = "orders_semantic dimensions region metrics total_revenue"

compiled = compile_request(conn, request)
print(compiled.sql)

rows = execute_request(conn, request).fetchall()
```

Core query functions:

- `parse_request(request)`
- `compile_request(conn, request)`
- `compile_request_sql(conn, request)`
- `execute_request(conn, request)`

## Introspection

These helpers are useful when building higher-level integrations:

- `list_semantic_views(conn)`
- `get_semantic_view(conn, view_name)`

## dbt Plugin Registration

If you are integrating directly with a DuckDB connection that should expose the dbt helper functions, use:

```python
from semduck import register_connection

register_connection(conn)
```

That initializes the registry and registers the plugin functions used by the dbt integration.

## What This Guide Does Not Treat As Stable

The package exports additional service, agent, MCP, and LLM configuration symbols. Those are useful for advanced integrations, but this docs site treats them as secondary until the public surface settles.
