# Python API

The documented Python surface is intentionally small. Start with the functions in `semduck.api`.

## Registry And Loading

```python
import duckdb
from semduck import init_registry, load_semantic_yaml_file

conn = duckdb.connect("weather.duckdb")

# Initialize the registry objects in your connected db. This is required! 
init_registry(conn)

# Load a semantic definition. 
load_semantic_yaml_file(conn, "weather_semantic.yaml")
```

Core loaders:

- `init_registry(conn)`
- `load_semantic_yaml(conn, yaml_text)`
- `load_semantic_yaml_file(conn, path)`
- `load_semantic_ddl(conn, ddl_text)`
- `load_semantic_ddl_file(conn, path)`

This assumes a base table is already created in the database that `weather_semantic.yaml` references. 
The python API exposes methods to load semantic definitions in either yaml or ddl and either as a string or a file. 

## Lower-Level Loading Helpers

If you already have an in-memory semantic spec as a Python dictionary, use:

- `load_semantic_spec(conn, spec)`
- `check_semantic_spec(conn, spec)`

That usually means another Python layer has already assembled or transformed the semantic definition before Semduck sees it, for example in tests, internal tooling, or a higher-level authoring workflow.

## Compile And Execute

```python
from semduck import compile_request, execute_request

request = "weather dimensions location metrics day_count, avg_temp_max"

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

These helpers are useful when building higher-level interfaces:

- `list_semantic_views(conn)`
- `get_semantic_view(conn, view_name)`

## dbt Plugin Registration

If you are integrating directly with a DuckDB connection that should expose the dbt helper functions, use:

```python
from semduck import register_connection

register_connection(conn)
```

That initializes the registry and registers the plugin functions used by the dbt interface.

## What This Guide Does Not Treat As Stable

The package exports additional service, agent, MCP, and LLM configuration symbols. Those are useful for advanced interface usage, but this docs site treats them as secondary until the public surface settles.
