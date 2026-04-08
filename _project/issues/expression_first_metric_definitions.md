# Issue: Metric Definitions Should Be Expression-First

## Status

Open.

## Related Spec

- `_project/specs/expression_first_metrics.md`

## Implemented By

- None yet.

## Context

Semduck currently models metrics around aggregate metadata such as `metric_type`, especially in
YAML authoring and registry storage.

That means metric authors are not consistently writing the actual metric expression they want to
compile. Instead, they often have to split a metric into:

- an aggregate type such as `sum`, `count`, or `avg`
- an input expression that is not itself the full metric definition

This differs from the expression-first mental model that users expect from semantic-layer systems,
where a metric definition is the authored expression itself.

It also makes YAML and DDL feel like they follow different contracts:

- YAML requires explicit aggregate metadata
- DDL appears expression-first to the reader, but the loader still normalizes metrics into
  `metric_type + expr`

## Impact

The current model creates several kinds of friction:

- authors cannot rely on `expr` meaning "the actual metric definition"
- YAML and DDL do not share one clear metric authoring model
- examples and docs are harder to teach because aggregate metadata leaks into the public contract
- Semduck feels less consistent with other semantic-layer data models that treat metric
  definitions as expressions

## Current Workaround

Authors must define metrics using the current aggregate metadata model instead of simply writing the
metric expression they want Semduck to use.
