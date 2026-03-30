# Metric Fact/Metric References v1

## Status

Proposed.

## Addresses Issue

- `project/issues/metrics-compiling-from-facts.md`

## Implemented By

- None yet.

## Summary

Enable semantic-view metrics to reference same-table `facts` and same-table semantic `metrics`
without requiring recursive inlining of physical column expressions.

This enhancement keeps the authoring interface unchanged while changing metric compilation from
"treat `metric.expr` as raw physical-table SQL" to "resolve semantic dependencies, then compile in
ordered SQL stages." The goal is to support patterns like:

```yaml
facts:
  - name: order_revenue
    expr: order_total
  - name: order_profit
    expr: order_total - unit_costs

metrics:
  - name: revenue
    metric_type: sum
    expr: order_revenue
  - name: profit
    metric_type: sum
    expr: order_profit
  - name: margin_pct
    metric_type: expr
    expr: div0(profit, revenue)
```

The implementation should prefer staged alias materialization over fully recursive physical
expansion so compiled SQL stays readable and avoids repeated expression duplication.

## Key Changes

### Public Interface

Keep YAML and DDL authoring syntax unchanged.

- No registry schema changes.
- `facts` and `metrics` continue to store authored `expr` values as written.
- No new request syntax is required.

### Semantic Metric Resolution

Allow semantic-view metric definitions to resolve references to same-table semantic objects.

- Facts may be referenced by metrics on the same semantic table.
- Metrics may be referenced by other metrics on the same semantic table.
- Metric definition order in YAML or DDL must not matter.
- Cross-table references are out of scope for v1 and should fail with a clear
  `SemanticResolutionError`.

Resolution rules for metric expressions:

- Resolve same-table metric references first.
- Resolve same-table fact references second.
- Leave function calls such as `div0(...)` as SQL functions, not semantic identifiers.
- Bare identifiers that are not semantic objects remain physical SQL identifiers in the owning
  table context.

### Staged SQL Compilation

Implement semantic metric compilation using ordered SQL stages instead of recursively inlining all
physical expressions.

Preferred shape:

1. Row-grain base stage:
   - Project required fact expressions as aliases.
   - Project any row-level expressions needed as metric inputs.
2. Aggregate metric stage:
   - Compute aggregate named metrics such as `sum(order_revenue) as revenue`.
3. Post-aggregate formula stage:
   - Compute metric-on-metric formulas such as `div0(profit, revenue) as margin_pct`.

This keeps facts at row grain, preserves metrics as the aggregation boundary, and avoids expanding
the same physical expression into multiple downstream metrics.

### Dependency Analysis

Add same-table dependency analysis for semantic metric definitions.

- Build a dependency graph over facts and metrics referenced by each metric.
- Topologically order metric compilation independent of authoring order.
- Reject direct self-reference.
- Reject indirect cycles with a specific error that identifies the cycle.

### Planner / Compiler Changes

Refactor planner output so semantic metrics are no longer represented only as a single flat
pre-qualified SQL string.

The planner/compiler should explicitly track:

- which facts are required in the row-grain base stage
- which named metrics are aggregate outputs
- which named metrics belong in the post-aggregate formula stage

The current metric path that directly applies aggregation to `metric.expr` should be replaced with a
staged semantic compilation path. Existing request-time derived metric behavior should remain
supported, but it should compile against the staged named-metric outputs.

## Implementation Notes

- Keep v1 limited to same-table semantic references inside metric definitions.
- Do not recursively inline physical column structure as the primary strategy.
- Recursive expansion may be kept as a fallback only for edge cases where staged aliasing is not
  sufficient, but it should not be the default model.
- Facts remain row-level semantic aliases, not aggregate definitions.
- Aggregate metrics continue to define the aggregation boundary.
- Request-time derived metrics should continue to work on top of named semantic metrics produced by
  the new staged compilation path.

## Test Plan

Add coverage for these scenarios:

- A semantic-view metric can aggregate a same-table fact:
  - `revenue as sum(order_revenue)` compiles and executes correctly.
- Multiple metrics can share the same fact alias without duplicating its physical expression in SQL.
- A semantic-view metric can reference same-table named metrics:
  - `profit as sum(order_profit)`
  - `revenue as sum(order_revenue)`
  - `margin_pct as div0(profit, revenue)`
- Forward metric references work when the graph is acyclic.
- Multi-level same-table metric dependency chains work.
- Direct self-reference fails.
- Indirect metric cycles fail.
- Cross-table fact or metric references fail.
- Unknown semantic references fail with a clear error.
- Request-time derived metrics still work when their named metric inputs are built from facts.

Acceptance scenarios:

- A user can define a fact once and reference it from one or more semantic-view metrics.
- A user can define named metrics and then define a formula metric that references those named
  metrics.
- Compiled SQL uses staged projections/aggregations instead of duplicating long physical expressions
  throughout the metric graph.

## Assumptions And Defaults

- v1 supports semantic references only within the same semantic table.
- Fact and metric authoring syntax remains unchanged.
- Metric definition order does not matter.
- SQL function detection continues to rely on the existing identifier parsing behavior.
- Full recursive physical-expression expansion is not the primary implementation strategy.
