# Limitations

This project is still early. The docs should make the current boundaries explicit rather than implying a broader supported surface.

## Current Boundaries

- DuckDB is the supported execution engine.
- YAML definitions are supported in standalone Python and CLI workflows.
- dbt support uses inline semantic DDL, not YAML-in-dbt.
- The documented Python API is intentionally smaller than the full export list in `semduck.__init__`.

## Practical Constraints

- `ask` depends on external LLM provider configuration.
- MCP guidance assumes a local `stdio` server workflow.
- GitHub Pages docs are versionless for now; the site represents the latest `main`.
- DuckDB file locking still applies to Semduck examples that operate on a checked-in `.duckdb` file. Semduck processes must follow DuckDB's concurrency rules: either one process holds a read/write connection, or multiple processes hold read-only connections. See [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency). If another DuckDB process has that file open in a conflicting mode, close it first or copy the database to a temporary path.

## Documentation Policy

If a behavior is only implied by tests or internal modules and is not described in the guides or examples, treat it as implementation detail rather than committed public surface.
