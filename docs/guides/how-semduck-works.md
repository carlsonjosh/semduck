# How Semduck Works

Semduck has a small runtime model:

1. A semantic definition is authored in YAML or semantic DDL.
2. The definition is validated and loaded into a registry stored in DuckDB.
3. A user writes a semantic request against a named view.
4. The planner resolves dimensions, metrics, joins, and filters.
5. The compiler emits SQL.
6. The runtime optionally executes that SQL and returns rows.

## Registry

The registry is a DuckDB schema managed by `semduck init`. It stores semantic view metadata that the compiler uses when resolving a request.

## Definitions

Semduck supports two authoring formats:

- YAML for standalone Python and CLI usage
- semantic DDL for standalone usage and dbt integration

In dbt, semduck deliberately uses inline DDL rather than YAML-in-dbt. That keeps the Python runtime dbt-agnostic and avoids unresolved `ref(...)` or `source(...)` behavior in YAML.

## Request Compilation

A request starts with a view name and then asks for dimensions, metrics, and optional predicates. For example:

```text
orders_semantic dimensions customer_name metrics total_revenue where region = 'US'
```

Semduck parses that request, resolves the semantic objects from the registry, determines the required joins, rewrites predicates when needed, and returns compiled SQL.

## Execution Surfaces

The same core runtime powers multiple entrypoints:

- Python API functions in `semduck.api`
- CLI commands like `load`, `compile`, and `query`
- dbt plugin functions and macros
- FastMCP tools and resources
- the `ask` workflow built on top of the same compile/query services
