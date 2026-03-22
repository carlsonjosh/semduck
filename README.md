# duckdb-semantic

Portable semantic view runtime for DuckDB, implemented in Python.

## Quickstart

```bash
uv sync
uv run duckdb-semantic init-registry --db demo.duckdb
uv run duckdb-semantic load-yaml --db demo.duckdb --file examples/orders_semantic.yaml
uv run duckdb-semantic compile --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

## YAML Shape

Semantic YAML files must be a top-level mapping with:

- `name`: required semantic view name
- `tables`: required non-empty list of table definitions
- `description`: optional view description
- `joins`: optional list of joins between declared tables

Each table must include:

- `name`: required logical table name
- `base_table.table`: required physical table name

Optional table fields:

- `base_table.schema`
- `description`
- `primary_key.columns`
- `dimensions`
- `time_dimensions`
- `facts`
- `metrics`

`dimensions`, `time_dimensions`, and `facts` are lists of objects shaped like:

```yaml
- name: object_name
  expr: sql_expression
  data_type: optional_type
  description: optional_description
```

`metrics` are shaped like:

```yaml
- name: metric_name
  metric_type: sum
  expr: sql_expression
  default_agg: optional_default_agg
  description: optional_description
```

`joins` are shaped like:

```yaml
- name: join_name
  left_table: declared_left_table
  right_table: declared_right_table
  join_type: left
  join_expr: LEFT_TABLE.id = RIGHT_TABLE.id
  description: optional_description
```

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
        expr: order_id
```

More complete valid YAML:

```yaml
name: orders_semantic
description: Orders analytics semantic view

tables:
  - name: orders
    description: Order grain table
    base_table:
      schema: mart
      table: orders_base
    primary_key:
      columns: [order_id]
    dimensions:
      - name: region
        expr: region
        data_type: varchar
        description: Sales region
    time_dimensions:
      - name: order_date
        expr: order_date
        data_type: date
    facts:
      - name: revenue
        expr: revenue
        data_type: double
    metrics:
      - name: total_revenue
        metric_type: sum
        expr: revenue
      - name: order_count
        metric_type: count
        expr: order_id

  - name: customers
    base_table:
      schema: mart
      table: customers_base
    primary_key:
      columns: [customer_id]
    dimensions:
      - name: customer_segment
        expr: customer_segment
        data_type: varchar

joins:
  - name: orders_to_customers
    left_table: orders
    right_table: customers
    join_type: left
    join_expr: LEFT_TABLE.customer_id = RIGHT_TABLE.customer_id
```

Validation rules enforced by the loader:

- top-level YAML must be a mapping
- semantic view `name` is required
- `tables` must be a non-empty list
- every table needs a unique `name`
- every table needs `base_table.table`
- semantic object names must be unique within a table across `dimensions`, `time_dimensions`, `facts`, and `metrics`
- `dimensions`, `time_dimensions`, and `facts` entries require `name` and `expr`
- `metrics` entries require `name`, `metric_type`, and `expr`
- joins must reference declared tables and require `name`, `left_table`, `right_table`, `join_type`, and `join_expr`

## Development

```bash
uv sync
uv run pytest
```
