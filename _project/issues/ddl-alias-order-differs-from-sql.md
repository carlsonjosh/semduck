# Issue: Semantic DDL Uses Alias-First Expression Order

## Status

Committed.

## Related Spec

- None yet.

## Implemented By

- None yet.

## Context

Semantic DDL historically defined dimensions, facts, and metrics using alias-first syntax such as
`total_revenue as sum(order_total)`.

That is consistent within the semantic DSL, but it differs from core SQL projection order, where
the conventional form is `sum(order_total) as total_revenue`.

The mismatch creates friction in two places:

- users reading semantic DDL often expect SQL-style expression-first aliasing
- formula metrics now look especially surprising because they read like SQL expressions but still
  require semantic-name-first ordering

## Impact

The current shape is valid and implemented, but it increases the chance that users will:

- assume the examples are backwards or invalid
- write SQL-style metric definitions first and hit parser errors unless both forms are supported
- hesitate to adopt the DDL because it looks less SQL-like than expected

## Resolution

Semantic DDL now uses SQL-style expression-first aliasing, for example
`sum(order_total) as total_revenue` and `total_revenue / order_count as average_order_value`.

This was applied as a breaking change across the repo rather than through a compatibility window,
because the repo is still the only consumer.
