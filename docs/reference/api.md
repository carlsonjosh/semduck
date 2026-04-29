# API Surface

This page documents the stable, user-facing API surface that the docs site treats as primary.

## Core Functions

Registry and loading:

- `init_registry(conn)`: create the Semduck registry schema in a DuckDB connection.
- `load_semantic_yaml(conn, yaml_text, *, replace_existing=True, validate_only=False)`: parse YAML text, validate it, and optionally write it to the registry.
- `load_semantic_yaml_file(conn, path, *, replace_existing=True, validate_only=False)`: read YAML from a file, then validate and load it.
- `load_semantic_ddl(conn, ddl_text, *, replace_existing=True, validate_only=False)`: parse semantic DDL text, validate it, and optionally write it to the registry.
- `load_semantic_ddl_file(conn, path, *, replace_existing=True, validate_only=False)`: read semantic DDL from a file, then validate and load it.
- `load_semantic_spec(conn, spec, *, replace_existing=True, validate_only=False, source_yaml=None)`: validate and load an already-parsed semantic spec dictionary.
- `check_semantic_spec(conn, spec)`: validate an already-parsed semantic spec dictionary without writing it.

Requests and execution:

- `parse_request(request)`: parse a semantic request string into a structured request object.
- `compile_request(conn, request)`: compile a semantic request into a structured query result that includes SQL.
- `compile_request_sql(conn, request)`: compile a semantic request and return only the SQL string.
- `execute_request(conn, request)`: compile and execute a semantic request against DuckDB.

Introspection and interfaces:

- `list_semantic_views(conn)`: list registered semantic view names.
- `get_semantic_view(conn, view_name)`: return the resolved registry metadata for one semantic view.
- `register_connection(conn)`: initialize the registry and register the dbt DuckDB plugin functions on the connection.

## CLI Commands

- `semduck init`
- `semduck check`
- `semduck load`
- `semduck compile`
- `semduck query`
- `semduck ask`
- `semduck mcp`

## Advanced Exports

The package also exports service-layer, agent, LLM, and MCP helpers from `semduck.__init__`. Those may be useful for advanced interface usage, but they are not the primary user-facing surface this documentation set optimizes for.
