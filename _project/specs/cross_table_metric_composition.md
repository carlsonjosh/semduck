# Cross-Table Metric Composition

## Status

Proposed.

## Related Decisions

- `_project/decisions/metric_reference_stage_boundaries.md`

## Summary

Explore a future semantic-view design that allows metric definitions to compose semantic objects
from more than one table in the same semantic view.

This is intentionally out of scope for the current metric fact/metric references work. The current
implementation supports same-table semantic references only. Cross-table composition would require a
separate planner/compiler contract that compiles table-local metric components independently and
then combines them through explicit SQL stages such as CTEs or subqueries.

## Why This Needs A Separate Spec

Cross-table metric references are not just a broader version of same-table references. They force
additional semantic decisions:

- what grain each table-local metric component is computed at
- how join fanout is prevented or validated
- when aggregation happens relative to joins
- whether metrics are combined before or after aggregation
- how ambiguous names are resolved across tables
- how final combined metrics are expressed in authoring syntax

These decisions should not be inferred from the same-table metric reference implementation.

## Future Direction

The likely implementation shape is:

1. Compile table-local metric components independently.
2. Materialize those components in explicit per-table CTEs or subqueries.
3. Join or combine those staged results using declared semantic-view relationships.
4. Compute final cross-table formulas in a later SQL stage.

That shape would preserve table-local semantics and make grain transitions explicit instead of
implicitly mixing them inside one expression rewrite pass.

## Questions To Answer

- What syntax should declare a cross-table metric reference?
- Should cross-table metrics reference table-qualified semantic names, globally unique names, or a
  new explicit component block?
- At what stage are joins allowed relative to aggregation?
- Which join types and fanout patterns are valid?
- Should cross-table composition be limited to post-aggregate formulas at first?
- How are conflicting grains validated and surfaced to the user?

## Follow-Up

If this work moves forward, create a full design that defines:

- authoring syntax
- planner stages
- SQL compilation shape
- validation and error rules
- test matrix for grain, join, and ambiguity behavior
