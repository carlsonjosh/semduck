# dbt-semduck

dbt package for registering and querying semduck semantic views in `dbt-duckdb` projects.

## Usage

Add the package to `packages.yml` and configure the `semduck.dbt.plugin` plugin in your DuckDB profile.

Create an explicit semantic registration model using the `semduck_semantic` materialization:

```jinja
{{ config(materialized='semduck_semantic') }}

create semantic view orders_semantic as
table orders as {{ ref('orders') }}
  dimensions (
    region as region
  )
  metrics (
    sum(revenue) as total_revenue
  );
```

Downstream models can query a semantic request with:

```jinja
select *
from {{ dbt_semduck.from_query(
    ref('orders_semantic_node'),
    'dimensions region metrics total_revenue'
) }}
```

The request suffix can also be split across lines for readability:

```jinja-sql
select *
from {{ dbt_semduck.from_query(
    ref('orders_semantic_node'),
    'dimensions region
     metrics total_revenue'
) }}
```

`dbt_semduck.query(...)` still returns raw compiled SQL when you need to use the full query text directly.
This is useful when you want more of a CTE style pattern like...

```jinja-sql
with semduck_query as (
  {{ dbt_semduck.query(
    ref('orders_semantic_node'),
    'dimensions region
     metrics total_revenue'
  ) }}
)

select * from semduck_query
```
