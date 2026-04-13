# dbt

`dbt-semduck` is the dbt-facing integration layer for semduck in `dbt-duckdb` projects.

## Package Boundary

- `semduck` owns the runtime, compiler, registry, CLI, Python API, and DuckDB plugin code.
- `dbt-semduck` owns dbt macros and the `semduck_semantic` materialization.

In dbt, the supported registration path is inline semantic DDL. YAML-in-dbt is not supported.

## Setup

1. Install the Python package with dbt support:

```bash
pip install "semduck[dbt]"
```

2. Add `dbt-semduck` to `packages.yml`.

3. Configure the DuckDB plugin in `profiles.yml`:

```yaml
outputs:
  dev:
    type: duckdb
    path: "jaffle_shop.duckdb"
    module_paths:
      - "../../packages/semduck/src"
    plugins:
      - module: semduck.dbt.plugin
```

The example project under `examples/dbt_example` shows a complete working configuration.

## Register A Semantic View

Create a dbt model using the `semduck_semantic` materialization:

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

The model loads the semantic definition into the registry and produces a lightweight relation containing the semantic view name.

The dbt model name and the semantic view name are separate concepts:

- `ref('sev_orders')` points at the dbt model that registers the semantic definition.
- `create semantic view orders as ...` defines the semantic view name used inside Semduck requests.

## Query From Downstream Models

Use `from_query(...)` when you want a `FROM`-safe relation:

```jinja
select *
from {{ dbt_semduck.from_query(
    ref('sev_orders'),
    'dimensions customer_name metrics total_revenue'
) }}
```

Use `query(...)` when you want raw compiled SQL, usually in a CTE:

```jinja
with semduck_query as (
  {{ dbt_semduck.query(
      ref('sev_orders'),
      'dimensions customer_name metrics total_revenue'
  ) }}
)

select *
from semduck_query
```

## Working Example

The repository example includes:

- source seeds
- ordinary dbt models
- a semantic registration model
- downstream models using both `from_query(...)` and `query(...)`

Run it from `examples/dbt_example`:

```bash
dbt deps --profiles-dir .
dbt seed --profiles-dir .
dbt run --profiles-dir .
```

The checked-in `jaffle_shop.duckdb` file is an ordinary DuckDB database. Semduck processes must follow DuckDB's concurrency rules: either one process holds a read/write connection, or multiple processes hold read-only connections. See [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency). If another DuckDB process already has this file open in a conflicting mode, close that session first or copy the file to a temporary path before querying it.
