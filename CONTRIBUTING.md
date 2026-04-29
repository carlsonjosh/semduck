# Contributing

Semduck keeps the core runtime, dbt package, docs, and examples in one repository. This guide covers the basic local workflow for making changes.

## Setup

From the repository root:

```bash
uv sync
```

That installs the project and the local development dependencies into the repo-managed virtual environment.

## Run Tests

Run the default Python test suite with:

```bash
uv run --group dev python -m pytest
```

Some changes may also need targeted integration coverage, especially around dbt behavior and examples.

## Repo Areas

- `packages/semduck`: core runtime, CLI, compiler, MCP server, and ask workflow
- `packages/dbt-semduck`: dbt macros and materializations
- `docs`: documentation site content
- `examples`: runnable examples and fixtures
- `integration_tests`: broader end-to-end coverage

## Documentation Changes

If you change public behavior, update the relevant docs page alongside the code. Keep interface docs focused on how users interact with Semduck, and keep contributor workflow details in this file rather than the installation docs.

## Before Opening A Change

- make sure the relevant tests pass
- update docs or examples when behavior changes
- keep changes scoped to the problem you are solving
