# Request Language

Semduck requests are semantic, compact, and view-centric.

## General Shape

```text
<view_name> dimensions <dimension list> metrics <metric list> where <optional predicate>
```

Examples:

```text
orders_semantic dimensions region metrics total_revenue
orders_semantic dimensions customer_name, order_date metrics total_revenue, item_count where region = 'US'
```

## Request Parts

- view name: the registered semantic view to query
- dimensions: one or more dimensions to group by
- metrics: one or more metrics to calculate
- where: an optional semantic predicate

## Compile Before Query

When building an interface, especially with MCP or AI tooling, semduck works best when you compile first and only execute after the request succeeds.

CLI:

```bash
semduck compile --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

Python:

```python
from semduck import compile_request

compiled = compile_request(
    conn,
    "orders_semantic dimensions region metrics total_revenue",
)
print(compiled.sql)
```

## Common Failure Modes

- unknown view name
- unknown dimension or metric
- invalid predicate referencing objects not available in the view
- malformed request syntax

When a request fails, inspect the view metadata, adjust the semantic request, and recompile rather than dropping to handwritten SQL.
