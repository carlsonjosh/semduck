# semduck monorepo

## Repo Layout

- [packages/semduck](/Users/joshuacarlson/repos/duckdb_sem_view_extension/packages/semduck): Python package containing the runtime, CLI, compiler, registry, and DuckDB plugin code
- [packages/dbt-semduck](/Users/joshuacarlson/repos/duckdb_sem_view_extension/packages/dbt-semduck): dbt package containing macros and materializations for semantic view registration and query macros
- [integration_tests](/Users/joshuacarlson/repos/duckdb_sem_view_extension/integration_tests): end-to-end test entry points
- [examples/dbt_jaffle_shop](/Users/joshuacarlson/repos/duckdb_sem_view_extension/examples/dbt_jaffle_shop): example dbt project using `semduck_semantic` and `dbt_semduck.query(...)`
- [examples/test_fixtures](/Users/joshuacarlson/repos/duckdb_sem_view_extension/examples/test_fixtures): source fixture projects used by automated integration tests

## Workspace Notes

The root [`pyproject.toml`](/Users/joshuacarlson/repos/duckdb_sem_view_extension/pyproject.toml) defines a Python workspace for [`packages/semduck`](/Users/joshuacarlson/repos/duckdb_sem_view_extension/packages/semduck). [`packages/dbt-semduck`](/Users/joshuacarlson/repos/duckdb_sem_view_extension/packages/dbt-semduck) is intentionally a dbt package rather than a Python workspace member.

The package boundary is:

- [`packages/semduck`](/Users/joshuacarlson/repos/duckdb_sem_view_extension/packages/semduck) owns the Python runtime, compiler, registry, CLI, and Python-side DuckDB integration surface
- [`packages/dbt-semduck`](/Users/joshuacarlson/repos/duckdb_sem_view_extension/packages/dbt-semduck) owns dbt-facing macros and materializations
