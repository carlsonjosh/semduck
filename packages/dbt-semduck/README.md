# dbt-semduck

dbt package for registering and querying semduck semantic views in `dbt-duckdb` projects.

This package is the dbt-facing half of the semduck integration. The Python runtime, compiler, registry, CLI, and DuckDB plugin live in `packages/semduck`.

## Usage

Add the package to `packages.yml` and configure the `semduck.dbt.plugin` plugin in your DuckDB profile.

Create an explicit semantic registration model using the `semduck_semantic` materialization:

```jinja
{{ config(materialized='semduck_semantic') }}

create semantic view orders as
table {{ ref('orders') }} as orders
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
    ref('sev_orders'),
    'dimensions region metrics total_revenue'
) }}
```

The request suffix can also be split across lines for readability:

```jinja-sql
select *
from {{ dbt_semduck.from_query(
    ref('sev_orders'),
    'dimensions region
     metrics total_revenue'
) }}
```

`dbt_semduck.query(...)` still returns raw compiled SQL when you need to use the full query text directly.
This is useful when you want more of a CTE style pattern like...

```jinja-sql
with semduck_query as (
  {{ dbt_semduck.query(
    ref('sev_orders'),
    'dimensions region
     metrics total_revenue'
  ) }}
)

select * from semduck_query
```

`sev_orders` is the dbt model name. The semantic view name comes from the DDL itself, so the request suffix above is compiled against `orders`, not against the dbt node name.

See `examples/dbt_example` for a complete working project, including `profiles.yml`, package installation, semantic registration, and downstream query models.
