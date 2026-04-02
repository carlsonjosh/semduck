# semduck monorepo

## Repo Layout

- [`packages/semduck`](packages/semduck): Python package containing the runtime, CLI, compiler, registry, and DuckDB plugin code
- [`packages/dbt-semduck`](packages/dbt-semduck): dbt package containing macros and materializations for semantic view registration and query macros
- [`integration_tests`](integration_tests): end-to-end test entry points
- [`examples/dbt_jaffle_shop`](examples/dbt_jaffle_shop): example dbt project using `semduck_semantic` and `dbt_semduck.query(...)`
- [`examples/test_fixtures`](examples/test_fixtures): source fixture projects used by automated integration tests

## Workspace Notes

The root [`pyproject.toml`](pyproject.toml) defines a Python workspace for [`packages/semduck`](packages/semduck). [`packages/dbt-semduck`](packages/dbt-semduck) is intentionally a dbt package rather than a Python workspace member.

The package boundary is:

- [`packages/semduck`](packages/semduck) owns the Python runtime, compiler, registry, CLI, and Python-side DuckDB integration surface
- [`packages/dbt-semduck`](packages/dbt-semduck) owns dbt-facing macros and materializations

## Compatibility Baseline

- Python: `3.11` through `3.12`
- DuckDB: `1.4+`
- dbt integration: `dbt-duckdb` `1.10.x` or newer within the supported range

## Tox

Use `tox` to run the local compatibility matrix:

```bash
uv sync
uv run tox
```

Useful targeted runs:

```bash
uv run tox -e py311-core-duckdb14
uv run tox -e py311-dbt
uv run tox -e py312-core-latest
uv run tox -e py312-dbt
```
