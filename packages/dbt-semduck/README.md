# dbt-semduck

dbt package for loading semduck semantic YAML files in `dbt-duckdb` projects.

## Usage

Add the package to `packages.yml`, configure the `semduck.dbt.plugin` plugin in your DuckDB profile, and add this hook to your project:

```yaml
on-run-start:
  - "{{ dbt_semduck.semduck_on_run_start() }}"
```

Then colocate semantic YAML files with models using the `<model_name>.semantic.yml` naming convention.

Downstream models can query a semantic request with:

```jinja
select *
from (
  {{ dbt_semduck.semduck_query("orders_semantic dimensions region metrics total_revenue") }}
)
```
