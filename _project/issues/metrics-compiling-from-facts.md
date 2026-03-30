# Issue: Metrics Compiling From Physical Expressions Instead Of Facts

## Status

Open.

## Related Spec

- `project/specs/metric_fact_metric_references.md`

## Implemented By

- None yet.

## Context

Named metrics currently compile against physical table expressions, not previously declared facts.
That means helper facts like `item_count_value` do not get substituted inside metric definitions, so
metric authors have to define metrics directly on the underlying columns instead of referencing the
semantic fact once.

This limits the semantic authoring model in two ways:

- a fact cannot be defined once and reused across multiple named metrics
- a semantic metric cannot cleanly build on top of another semantic metric

## Current Workaround

Define the metric directly on the underlying physical column or expression instead of referencing a
named fact or named metric.
