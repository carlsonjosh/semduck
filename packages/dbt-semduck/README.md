# dbt-semduck

dbt package for loading semduck semantic YAML files in `dbt-duckdb` projects.

## Usage

Add the package to `packages.yml` and configure the `semduck.dbt.plugin` plugin in your DuckDB profile.

Create an explicit semantic registration model using the `semduck_semantic` materialization:

```jinja
-- depends_on: {{ ref('orders') }}

{{ config(materialized='semduck_semantic') }}

create semantic view orders_semantic as
table orders as {{ ref('orders') }}
  dimensions (
    region as region
  )
  metrics (
    total_revenue as sum(revenue)
  );
```

Downstream models can query a semantic request with:

```jinja
-- depends_on: {{ ref('orders_semantic') }}

select *
from (
  {{ dbt_semduck.semduck_query("orders_semantic dimensions region metrics total_revenue") }}
)
```
