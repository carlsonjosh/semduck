# dbt_semduck Jaffle Shop Example

This is a small dbt-duckdb example showing how to define and query a semantic view with `dbt-semduck`.

## Files

- `seeds/customers.csv` and `seeds/orders.csv`: source data
- `models/fct_orders.sql` and `models/dim_customers.sql`: dbt models
- `models/orders_semantic_node.sql`: semantic DDL model using `semduck_semantic`
- `models/customer_revenue_report.sql`: downstream semantic query model

## Profile

This example includes a local [`profiles.yml`](/Users/joshuacarlson/repos/duckdb_sem_view_extension/examples/dbt_jaffle_shop/profiles.yml) with project-relative defaults:

- DuckDB database at `examples/dbt_jaffle_shop/jaffle_shop.duckdb`
- `module_paths` pointed at `../../packages/semduck/src`

## Run

From this directory:

```bash
dbt deps --profiles-dir .
dbt seed --profiles-dir .
dbt run --profiles-dir .
```

The semantic node registers `orders_semantic`, and the final model queries it with:

```jinja
{{ dbt_semduck.query(
    ref('orders_semantic_node'),
    'dimensions customer_name
     metrics total_revenue, total_revenue / 1000 as revenue_in_thousands'
) }}
```
