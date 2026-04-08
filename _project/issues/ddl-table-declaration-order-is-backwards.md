# Issue: Semantic DDL Table Declaration Order Is Backwards

## Status

Open.

## Related Spec

- None yet.

## Implemented By

- None yet.

## Context

Semantic DDL currently declares tables using the pattern:

```sql
table orders as fct_orders
```

That reads as semantic-name-first, physical-relation-second.

For users reading the DDL as SQL-shaped authoring, the more natural order is:

```sql
table fct_orders as orders
```

where the physical relation appears first and the semantic alias appears second.

## Impact

The current order creates avoidable confusion:

- it reads backwards relative to how users typically parse `source as alias`
- it makes example DDL harder to skim quickly
- it increases the chance that users will write the declaration in the opposite order and hit parser errors
- it weakens the SQL-like feel of semantic DDL even when the rest of the statement is expression-first

## Current Workaround

Authors must remember that table declarations are currently semantic-name-first rather than
physical-relation-first when writing semantic DDL.
