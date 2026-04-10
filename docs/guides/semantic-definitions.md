# Semantic Definitions

Semduck supports two definition formats: YAML and semantic DDL.

## Which One To Use

- Use YAML for standalone Python and CLI workflows.
- Use semantic DDL when working in dbt or when you prefer SQL-shaped definitions.

## YAML

Minimal valid YAML:

```yaml
name: sample
tables:
  - name: orders
    base_table:
      table: orders_base
    dimensions:
      - name: region
        expr: region
    metrics:
      - name: order_count
        metric_type: count
        expr: count(order_id)
```

Optional fields for dimensions and metrics can make the definition more self-describing:

```yaml
name: orders_semantic
description: Orders analytics semantic view
tables:
  - name: orders
    base_table:
      schema: mart
      table: orders_base
    dimensions:
      - name: region
        expr: region
        data_type: varchar
        description: Sales region used for grouping
    metrics:
      - name: total_revenue
        expr: sum(revenue)
        description: Sum of order revenue
      - name: margin_pct
        expr: total_profit / total_revenue
        description: Profit margin ratio
```

Supported optional fields in YAML today:

- semantic view: `description`
- table: `description`
- dimensions, time dimensions, and facts: `data_type`, `description`
- metrics: `description`
- joins: `description`

Validation rules enforced by the loader:

- top-level content must be a mapping
- `name` is required
- `tables` must be a non-empty list
- each table needs a unique `name`
- each table needs `base_table.table`
- semantic object names must be unique within a table
- dimensions, time dimensions, and facts require `name` and `expr`
- metrics require `name` and `expr`
- joins must reference declared tables and include the required join fields

Reference example: `packages/semduck/examples/orders_semantic.yaml`

## Semantic DDL

Example:

```sql
create semantic view orders_semantic as
table main.orders as orders
  primary key (order_id)
  dimensions (
    region as region type varchar description 'Sales region used for grouping'
  )
  metrics (
    sum(revenue) as total_revenue description 'Sum of order revenue',
    total_revenue / count(order_id) as avg_order_value description 'Average revenue per order'
  );
```

DDL optional fields mirror the same ideas:

- dimensions, time dimensions, and facts can include `type` and `description`
- metrics can include `description`
- tables and joins can include a separate `description '...'` line

Reference examples:

- `examples/dbt_example/models/sev_orders.sql`
- `packages/dbt-semduck/README.md`

## dbt Boundary

dbt support is intentionally narrower:

- supported: inline semantic DDL compiled by dbt and loaded into semduck
- not supported: YAML specs inside dbt with unresolved `ref(...)` or `source(...)`

That boundary keeps the runtime dbt-agnostic and matches the current package split between `semduck` and `dbt-semduck`.
