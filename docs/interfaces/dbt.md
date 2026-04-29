# dbt

`dbt-semduck` is the dbt-facing interface layer for semduck in `dbt-duckdb` projects.

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
    path: "weather.duckdb"
    module_paths:
      - "../../packages/semduck/src"
    plugins:
      - module: semduck.dbt.plugin
```

The example project under `examples/dbt_example` shows a complete working configuration.

## Materialize The Base Table

Before registering a semantic view, create the physical table the view will reference. For the weather example, a plain dbt model can materialize `weather_raw` from `read_csv(...)`:

```sql
{{ config(materialized='table') }}

select *
from read_csv('{{ var("weather_csv_path", "weather.csv") }}', auto_detect=true)
```

This part works the same way as any other DuckDB `read_csv(...)` model in dbt. Semduck starts after you already have a normal dbt relation to point at.

## Register A Semantic View

Create a dbt model named `sev_weather` using the `semduck_semantic` materialization, note that at the moment, only the DDL materialization strategy works with dbt:

```jinja
{{ config(materialized='semduck_semantic') }}

create semantic view weather as
table {{ ref('weather_raw') }} as weather
  time_dimensions (
    date as date type date
  )
  dimensions (
    location as location type varchar,
    weather as weather type varchar
  )
  facts (
    precipitation as precipitation type double,
    temp_max as temp_max type double
  )
  metrics (
    count(*) as day_count,
    avg(temp_max) as avg_temp_max,
    sum(precipitation) as total_precipitation
  );
```

The model loads the semantic definition into the registry and produces a lightweight relation containing the semantic view name.

The dbt model name and the semantic view name are separate concepts:

- `sev_weather` is the model name that can be referenced in downstream queries.
- `ref('weather_raw')` points at the dbt model that the semantic view should be created from.
- `create semantic view weather as ...` defines the semantic view name used inside Semduck requests. In this case `weather`.

## Query From Downstream Models

Use `from_query(...)` when you want a `FROM`-safe relation:

```jinja
select *
from {{ dbt_semduck.from_query(
    ref('sev_weather'),
    'dimensions location metrics day_count, avg_temp_max'
) }}
```

Use `query(...)` when you want raw compiled SQL, usually in a CTE:

```jinja
with semduck_query as (
  {{ dbt_semduck.query(
      ref('sev_weather'),
      "dimensions date_trunc('month', date) as month, location metrics total_precipitation"
  ) }}
)

select *
from semduck_query
```

## Build The Project

Once you have the raw model, the semantic registration model, and any downstream query models, compile and materialize them with standard dbt commands:

```bash
dbt deps --profiles-dir .
dbt build --profiles-dir .
```

`dbt build` will run the usual dbt flow for this project, including creating the base relation, registering the semantic view, and materializing downstream models that query it.

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

The snippets above use the same `weather` semantic view shape as the main quickstart so the transition is easier. The checked-in example project still uses the `jaffle_shop` sample data and an `orders` semantic view.

The checked-in `jaffle_shop.duckdb` file is an ordinary DuckDB database. Semduck processes must follow DuckDB's concurrency rules: either one process holds a read/write connection, or multiple processes hold read-only connections. See [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency). If another DuckDB process already has this file open in a conflicting mode, close that session first or copy the file to a temporary path before querying it.
