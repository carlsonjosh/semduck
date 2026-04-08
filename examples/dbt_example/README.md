# dbt_semduck Jaffle Shop Example

This is a small dbt-duckdb example showing how to define and query a semantic view with `dbt-semduck`.

## Files

- `seeds/customers.csv` and `seeds/orders.csv`: source data
- `models/fct_orders.sql` and `models/dim_customers.sql`: dbt models
- `models/sev_orders.sql`: semantic DDL model using `semduck_semantic`
- `models/rpt_customer_revenue.sql`: downstream semantic query model using `from_query(...)`
- `models/rpt_customer_revenue_wrapped.sql`: downstream semantic query model using raw `query(...)`

## Profile

This example includes a local [`profiles.yml`](profiles.yml) with project-relative defaults:

- DuckDB database at `examples/dbt_example/jaffle_shop.duckdb`
- `module_paths` pointed at `../../packages/semduck/src`

## Run

From this directory:

```bash
dbt deps --profiles-dir .
dbt seed --profiles-dir .
dbt run --profiles-dir .
```

The semantic node registers `orders_semantic`, and the example shows both downstream query styles.

Use `from_query(...)` when you want a `FROM`-safe relation without writing parentheses yourself:

```jinja
select *
from {{ dbt_semduck.from_query(
    ref('sev_orders'),
    'dimensions customer_name
     metrics total_revenue, total_revenue / 1000 as revenue_in_thousands'
) }}
```

Use `query(...)` when you want the raw compiled SQL text directly. A simple pattern is to put it in a CTE and select from that:

```jinja
with semduck_query as (
  {{ dbt_semduck.query(
      ref('sev_orders'),
      'dimensions customer_name
       metrics total_revenue'
  ) }}
)

select *
from semduck_query
```

See the main docs site for installation, package boundaries, and a broader dbt integration guide.
