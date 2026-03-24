# Design Decision: Remove YAML-In-dbt Support

## Status

Accepted.

## Context

`semduck` supports two standalone authoring formats:

- YAML specs loaded through the Python API or CLI
- semantic DDL loaded through the Python API, CLI, or `dbt-semduck`

Earlier versions of the `dbt-semduck` package also supported loading YAML files from dbt. That path required dbt-specific relation resolution logic inside `semduck` so YAML files could contain unresolved base table references that were later converted into concrete relations.

That created an architectural leak:

- `semduck` was no longer only a semantic runtime and compiler
- `semduck` contained dbt-specific parsing and relation-resolution behavior
- the dbt package and the core Python package shared responsibility for dbt semantics in an unclear way

This conflicted with the intended boundary for the project.

## Decision

We removed YAML-in-dbt support.

`dbt-semduck` now supports semantic definitions in dbt through inline semantic DDL only. The dbt materialization passes compiled DDL into `semduck`, and `semduck` parses only concrete relations.

The core rule is:

- `semduck` must not require dbt parsing

That means `semduck` must not depend on unresolved dbt constructs such as:

- `ref(...)`
- `source(...)`
- dbt relation maps
- dbt graph inspection

`semduck` should only see already-normalized table references, in the same way the DDL path normalizes table names after dbt compilation.

## Why

This keeps the architecture clean:

- `semduck` remains dbt-agnostic
- `semduck` owns the Python-side DuckDB integration surface, but not dbt parsing
- `dbt-semduck` owns dbt-facing macros, materializations, and relation resolution before handoff
- inline DDL in dbt is natural because dbt already compiles SQL before execution
- the runtime registry only stores concrete physical relations

This also avoids maintaining two dbt integration paths:

- inline DDL with compiled concrete relations
- YAML with unresolved symbolic relations

The DDL path is the stronger primary path because it lets dbt do what dbt already does well: compile model SQL into concrete relation references before execution.

## Consequences

Current supported flows are:

- standalone `semduck`:
  - YAML
  - DDL
- Python-side DuckDB integration through the `semduck` plugin surface
- `dbt-semduck`:
  - inline semantic DDL only

Current unsupported flow:

- YAML specs in dbt that require `semduck` to understand dbt syntax directly

## What It Would Take To Add YAML-In-dbt Back

If YAML-in-dbt is desired in the future, it must not reintroduce dbt parsing into `semduck`.

That means the YAML handed to `semduck` would need to contain already-normalized table references, matching the same concrete shape used by the DDL path. In practice, `base_table` would need to be resolved before `semduck` sees the spec, for example:

```yaml
base_table:
  schema: main
  table: orders
```

or, if carried through:

```yaml
base_table:
  database: analytics
  schema: main
  table: orders
```

Not this:

```yaml
base_table:
  ref: orders
```

or:

```yaml
base_table:
  source:
    name: raw
    table: orders
```

If we add YAML-in-dbt back, one of these must happen:

1. The dbt package compiles and resolves the YAML before calling `semduck`

This would mean `dbt-semduck` is responsible for:

- reading the YAML text
- resolving dbt relations into concrete names
- either passing a normalized spec dict to `semduck`
- or passing normalized YAML text to `semduck`

2. The dbt package passes YAML text that is already concrete

This is the same idea with a different transport:

- dbt handles resolution
- `semduck` just parses normal YAML

Both options are acceptable.

The non-acceptable option is:

- adding dbt-aware YAML relation parsing back into `semduck`

## Preferred Future Shape

If YAML-in-dbt returns, the preferred design is:

- dbt resolves table references first
- the resolved relation names are passed to `semduck`
- `semduck` parses only concrete YAML

In other words, the YAML path must match the same normalization contract as the DDL path.
