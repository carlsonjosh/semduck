# Semantic View Inference v1

## Summary

Add a semantic view inference feature that inspects a DuckDB table and produces a standard semduck
spec, then optionally loads it into the registry. In v1, inferred semantics will follow this
policy:

- Primary key/entity:
  - Use an explicitly supplied `entity_id` column when provided.
  - Otherwise inspect DuckDB metadata for a declared primary key.
  - If neither exists, generate the spec without an entity/primary key.
- Time-like columns become `time_dimensions`.
- String and boolean columns become `dimensions`.
- Numeric columns become `facts`.
- Metrics are auto-generated as:
  - `row_count` with `metric_type: count` and `expr: *`
  - `total_<fact_name>` with `metric_type: sum` and `expr: <fact_name>` for every inferred fact

This keeps inference aligned with the current compiler/runtime model, which already expects explicit
metric aggregations.

## Key Changes

### Public API

Add Python APIs for three layers of use:

- `infer_semantic_spec(conn, table_name, *, view_name=None, schema=None, entity_id=None, include_columns=None, exclude_columns=None) -> dict`
  - Returns a validated semduck spec dictionary without writing anything.
- `load_inferred_semantic_view(conn, table_name, *, view_name=None, schema=None, entity_id=None, include_columns=None, exclude_columns=None, replace_existing=True, validate_only=False) -> LoadResult`
  - Calls inference, validates the generated spec, and writes it through the existing loader path.
- Export both from `semduck.__init__`.

Behavior defaults:

- `view_name` defaults to `<base_table_name>_semantic`.
- The inferred semantic table name defaults to the base table name without schema qualification.
- `table_name` may be passed as `schema.table` or with `schema=` separately; normalize to the
  existing `base_table` shape used by semduck specs.
- `include_columns` and `exclude_columns` are optional guardrails for v1 so callers can avoid
  obviously wrong fields without needing custom inference hooks.

### Inference Subsystem

Add a new authoring/introspection module that:

- Reads DuckDB column metadata for the target table, including name, logical type, nullability if
  available, and ordinal position.
- Reads DuckDB constraint metadata to discover a declared primary key when present.
- Normalizes type classes into semantic categories:
  - `DATE`, `TIMESTAMP`, `TIMESTAMPTZ`, `TIME` -> `time_dimensions`
  - `VARCHAR`, `TEXT`, `CHAR`, `BOOLEAN` -> `dimensions`
  - integer, decimal, float, double, hugeint, numeric-family -> `facts`
  - unsupported or complex types are skipped in v1
- Preserves the source column name as both the semantic object name and `expr`.
- Copies the DuckDB type string into `data_type` for inferred dimensions, time dimensions, and
  facts.
- Builds metrics only from inferred facts:
  - one `row_count`
  - one `total_<column>` per fact
- Builds `primary_key.columns` only when an explicit or discovered key exists.
- Produces no joins and only one semantic table in v1.

Primary-key precedence:

1. `entity_id` argument, if provided and present on the table
2. metadata-discovered declared primary key
3. omit `primary_key` entirely

Failure behavior:

- Error if the target relation does not exist.
- Error if `entity_id` is provided but is not a valid column on the target relation.
- Error if `include_columns` names unknown columns.
- Do not error when no PK is available; generate a valid spec without one.
- Do not error when a table has zero inferred facts; still emit `row_count` if the table is
  otherwise inferable.

### CLI

Add a new `semduck infer` command:

- Required:
  - `--db`
  - `--table`
- Optional:
  - `--schema`
  - `--view-name`
  - `--entity-id`
  - `--include-columns`
  - `--exclude-columns`
  - `--load`
  - `--no-replace`

CLI behavior:

- Default mode prints the inferred spec as YAML to stdout.
- `--load` initializes the registry if needed, loads the inferred spec, and prints `ok load view_name=<name>`.
- Without `--load`, the command is non-mutating and acts as an authoring aid.
- `--include-columns` and `--exclude-columns` accept comma-separated column names.

Keep v1 out of dbt/UDF/plugin surfaces. The feature should exist only in the Python package and
standalone CLI.

## Implementation Notes

- Reuse `validate_semantic_spec()` and `load_semantic_spec()` so inferred specs go through the exact
  same validation and persistence path as hand-authored specs.
- Keep inference separate from planner/compiler code; no changes should be required there.
- Add a small metadata access helper layer so DuckDB-specific catalog queries are isolated and easy
  to evolve if catalog access differs by version.
- Use deterministic ordering:
  - preserve source column order for inferred dimensions/time dimensions/facts
  - emit generated metrics in source fact order, with `row_count` first
- Skip unsupported DuckDB types in v1 rather than trying to coerce them.

## Test Plan

Add unit/integration coverage for these scenarios:

- Inference from a table with:
  - explicit PK metadata
  - text, boolean, date/timestamp, and numeric columns
  - expected split into dimensions, time_dimensions, facts, and generated metrics
- Explicit `entity_id` overrides metadata PK selection.
- Missing metadata PK plus no `entity_id` yields a valid spec with no `primary_key`.
- Provided `entity_id` that does not exist fails with a clear validation/inference error.
- `row_count` is always created.
- `total_<fact>` metrics are created for each inferred fact and use `metric_type: sum`.
- Unsupported column types are skipped, not misclassified.
- `include_columns` limits inference to the requested subset.
- `exclude_columns` removes requested columns from inference.
- CLI infer prints YAML for a valid table.
- CLI infer `--load` writes the inferred view and it can be retrieved with `get_semantic_view()` or
  compiled.

Acceptance scenarios:

- A user can point semduck at an existing DuckDB table and get a usable spec with no manual YAML.
- Inferred views remain fully compatible with existing registry, planner, and SQL compilation
  behavior.

## Assumptions And Defaults

- Specs without an entity/primary key are valid in v1.
- Complex/nested/collection types are ignored in v1 rather than exposed as semantic objects.
- The CLI prints YAML rather than JSON by default because it is the repo’s primary authoring format
  outside dbt.
