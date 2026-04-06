# Expression-First Metrics

## Status

Proposed.

## Addresses Issue

- `_project/issues/expression_first_metric_definitions.md`

## Implemented By

- None yet.

## Summary

Remove `metric_type` and `default_agg` from the public Semduck metric model and make metric `expr`
the canonical authored definition in both YAML and semantic DDL.

After this change, a metric definition should describe the actual SQL expression Semduck compiles,
for example:

```yaml
metrics:
  - name: order_count
    expr: count(order_id)
  - name: total_revenue
    expr: sum(order_total)
  - name: average_order_value
    expr: total_revenue / order_count
```

This is a breaking change applied consistently across authoring, registry storage, planner
behavior, docs, and examples.

## Key Changes

### Public Authoring Model

- YAML metrics require `name` and `expr`.
- YAML metrics no longer accept `metric_type`.
- YAML metrics no longer accept `default_agg`.
- DDL metrics preserve the authored expression exactly instead of decomposing aggregate calls into
  aggregate metadata.
- Request syntax remains unchanged.

### Registry Model

- Remove `metric_type` from `semantic.metrics`.
- Remove `default_agg` from `semantic.metrics`.
- Update `semantic.v_metrics` to expose only the expression-first metric shape.
- Update registry reader and writer code to store and reconstruct metrics without aggregate
  metadata.

### Planner / Compiler Model

- Replace metric-type-driven compilation with expression-driven compilation.
- Detect aggregate metrics from their expressions rather than from a stored aggregate enum.
- Preserve the current staged metric-resolution behavior for same-table metric references, but make
  it work from the authored metric expression rather than from `metric_type`.
- Aggregate expressions such as `count(order_id)`, `count(distinct customer_id)`, `sum(order_total)`,
  and `avg(order_total)` should compile from the authored expression directly.
- Formula metrics such as `total_revenue / order_count` should continue to resolve against named
  semantic metrics using the staged metric plan.

## Implementation Notes

- Update YAML validation so metrics require only `name` and `expr`.
- Update the DDL loader so metric parsing no longer splits aggregate calls into `metric_type` and
  input expression.
- Remove `metric_type` and `default_agg` from semantic metric types where they are only used for
  metric resolution.
- Refactor the metric planner/compiler path so aggregate handling is based on expression analysis.
- Keep the existing protections against invalid mixes of row-level and aggregate references.
- Reject old authored definitions that still include `metric_type` or `default_agg`.

## Migration Notes

This is a hard break.

- Existing authored YAML definitions that use `metric_type` should fail validation until rewritten.
- Existing DDL definitions should be rewritten to the expression-first model where needed.
- Existing semantic registries need an explicit migration or rebuild path because `init_registry`
  currently relies on `create table if not exists` and does not remove old columns automatically.

The implementation must choose one of these explicit paths:

- add a registry migration that rewrites existing metric rows and rebuilds the schema, or
- document and enforce a re-init-and-reload workflow for existing registries

The implementation should not assume that registry schema updates happen automatically.

## Test Plan

- YAML loader accepts expression-first metrics with only `name` and `expr`.
- YAML loader rejects `metric_type` and `default_agg`.
- DDL loader stores metric expressions as authored.
- Aggregate metric expressions compile correctly:
  - `count(order_id)`
  - `count(distinct customer_id)`
  - `sum(order_total)`
  - `avg(order_total)`
- Same-table formula metrics continue to resolve correctly.
- Invalid mixes of aggregate and row-level references still fail with clear errors.
- Registry migration or registry rebuild behavior is tested or explicitly documented.
- Docs and examples are updated to the expression-first metric syntax only.

## Assumptions And Defaults

- This change is a hard break with no compatibility mode.
- `default_agg` is removed along with `metric_type`.
- Metric `expr` is the full canonical definition in both YAML and DDL.
- Request-language syntax does not change as part of this work.
- Existing registries must be migrated explicitly or rebuilt and reloaded.
