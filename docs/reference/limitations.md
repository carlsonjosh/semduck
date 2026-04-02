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

## Documentation Policy

If a behavior is only implied by tests or internal modules and is not described in the guides or examples, treat it as implementation detail rather than committed public surface.
