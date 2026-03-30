# Design Decision: Metric Reference Stage Boundaries

## Status

Proposed.

## Related Spec

- `_project/specs/metric_fact_metric_references.md`

## Context

The metric fact/metric references work now supports the core v1 patterns:

- aggregate metrics can reference same-table facts
- row-level helper metrics can feed aggregate metrics
- post-aggregate formula metrics can reference named aggregate metrics
- request-time derived metrics can work on top of both aggregate outputs and row-level helper
  aliases in ungrouped queries

That implementation introduced explicit stage boundaries:

1. row-grain base expressions
2. aggregate metric outputs
3. post-aggregate metric formulas

Those boundaries leave a few remaining questions that were not decision-completely specified in the
original v1 spec.

## Open Questions

- Should aggregate metrics be allowed to reference aggregate or post-aggregate metrics?
  - Example: `double_profit as sum(total_profit)`
  - This currently remains invalid because it mixes aggregation stages in a way that is not clearly
    defined by the current planner model.

- Should named formula metrics be allowed to mix aggregate metrics with row-level expressions in the
  same definition?
  - Example: `blended_margin as total_profit / order_revenue`
  - This currently remains invalid because it mixes row-grain and post-aggregate semantics in one
    expression.

- Should request-time derived metrics inherit the same mixed-stage rules as named metrics, or should
  they remain more restrictive?

- If broader mixed-stage support is added, should the planner normalize those expressions into
  additional subquery stages, or should some combinations remain invalid by design?

- Should semantic metrics ever be allowed to reference facts or metrics from another table in the
  same semantic view?
  - This is intentionally deferred to a separate spec because it requires table-local compilation,
    grain validation, and explicit combination stages.

## Current Decision

Do not widen the semantic contract further until these stage-boundary questions are explicitly
decided.

The current implementation should remain the supported behavior for the metric reference feature:

- same-table semantic references only
- helper row-level metrics may feed aggregate metrics
- aggregate metrics may feed post-aggregate formulas
- mixed row-level and aggregate references in one formula remain invalid
- aggregate metrics cannot aggregate over aggregate/post-aggregate metrics

## Why

The core fact/metric reference use cases are now supported, and they align with the staged compiler
shape in a predictable way.

The remaining combinations are not just parser gaps; they require a semantic decision about how
stages should compose. Leaving them undecided but implemented ad hoc would make the metric model
harder to reason about and harder to document.

## Follow-Up

If we want to widen the contract later, create a follow-on spec that answers:

- which stage combinations are valid
- how those combinations compile
- which combinations should remain invalid permanently
- what test matrix covers those rules

Cross-table composition should be explored separately in:

- `_project/specs/cross_table_metric_composition.md`
