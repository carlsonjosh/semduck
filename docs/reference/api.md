# API Surface

This page documents the stable, user-facing API surface that the docs site treats as primary.

## Core Functions

Registry and loading:

- `init_registry(conn)`
- `load_semantic_yaml(conn, yaml_text, *, replace_existing=True, validate_only=False)`
- `load_semantic_yaml_file(conn, path, *, replace_existing=True, validate_only=False)`
- `load_semantic_ddl(conn, ddl_text, *, replace_existing=True, validate_only=False)`
- `load_semantic_ddl_file(conn, path, *, replace_existing=True, validate_only=False)`
- `load_semantic_spec(conn, spec, *, replace_existing=True, validate_only=False, source_yaml=None)`
- `check_semantic_spec(conn, spec)`

Requests and execution:

- `parse_request(request)`
- `compile_request(conn, request)`
- `compile_request_sql(conn, request)`
- `execute_request(conn, request)`

Introspection and integration:

- `list_semantic_views(conn)`
- `get_semantic_view(conn, view_name)`
- `register_connection(conn)`

## CLI Commands

- `semduck init`
- `semduck check`
- `semduck load`
- `semduck compile`
- `semduck query`
- `semduck ask`
- `semduck mcp`

## Advanced Exports

The package also exports service-layer, agent, LLM, and MCP helpers from `semduck.__init__`. Those may be useful for advanced integrations, but they are not the primary user-facing surface this documentation set optimizes for.
