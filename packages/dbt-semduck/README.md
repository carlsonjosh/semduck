# dbt-semduck

dbt package for loading semduck semantic YAML files in `dbt-duckdb` projects.

## Usage

Add the package to `packages.yml` and configure the `semduck.dbt.plugin` plugin in your DuckDB profile.

Create an explicit semantic registration model using the `semduck_semantic` materialization:

```jinja
-- depends_on: {{ ref('orders') }}

{{ config(
    materialized='semduck_semantic',
    semduck_spec='semantic_specs/orders_metrics.yml'
) }}

select 'orders_semantic' as semantic_view_name
```

Downstream models can query a semantic request with:

```jinja
-- depends_on: {{ ref('orders_semantic') }}

select *
from (
  {{ dbt_semduck.semduck_query("orders_semantic dimensions region metrics total_revenue") }}
)
```
