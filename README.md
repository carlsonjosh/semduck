# semduck

Semantic views for DuckDB.

You should not need a cloud license to get a usable semantic layer. Semduck brings semantic views directly into DuckDB so you can define business logic once and reuse it locally across analysis workflows.

Stop rebuilding the same joins, metrics, and snippets. Define semantic views **once** in the database. Reuse them across queries, scripts, dbt pipelines, and machine workflows.

## How it works

Views are stored in DuckDB alongside your data for easy reuse later.

Query dimensions and metrics using a semantic request. Or use the `ask` framework to ask natural language questions and have a partner LLM (even one hosted locally) build and run the request for you. 

Humans can use it. Machines can use it. Both get the same semantic contract.

## Quick Example

```bash
pip install semduck

semduck init --db demo.duckdb
semduck load --db demo.duckdb --file orders_semantic.yaml
semduck query --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

Instead of writing SQL, you ask for the business objects you care about. Semduck resolves the view, joins, and metric definitions for you.

Semantic requests can be executed in Python, dbt, or a CLI. The `ask` framework can be used from Python, the CLI, or an MCP client.

## What A Semantic View Looks Like

### In YAML
```yaml
name: orders_semantic
tables:
  - name: orders
    base_table:
      table: orders
    time_dimensions:
      - name: order_date
        expr: order_date
    dimensions:
      - name: order_id
        expr: order_id
      - name: region
        expr: region
    metrics:
      - name: total_revenue
        expr: sum(order_total)
      - name: order_count
        expr: count(order_id)
```

### In DDL
```sql
create semantic view orders_semantic as
table orders as fct_orders
  primary key (order_id)
  time_dimensions (
    order_date as order_date
  )
  dimensions (
    order_id as order_id,
    region as region,
  )
  metrics (
    sum(order_total) as total_revenue,
    count(order_id) as order_count,
  )
```

## What A Semantic Request Looks Like

### In CLI
`semduck query --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"`

You can also use derived dimensions and metrics in the request...
`semduck query --db demo.duckdb --request "orders_semantic dimensions date_trunc('month', order_date) as order_month, region metrics total_revenue, order_count, total_revenue / order_count as average_ticket_size"`

Or use the ask framework to get assistance from an LLM (with a bit more configuration)...
`semduck ask --db demo.duckdb --config path/to/config.yaml --question "What is revenue by region?"`

### In a dbt project

```sql
select *
from {{
  dbt_semduck.from_query(
    ref('orders_semantic')
    dimensions
      date_trunc('month', order_date) as order_month, 
      region 
    metrics 
      total_revenue,
      order_count, 
      total_revenue / order_count as average_ticket_size
  )
}}
```

### In Python
 See the [Python package README](packages/semduck/README.md) for more examples.

The same runtime powers:

- Python and CLI workflows
- dbt projects through a dbt package `dbt-semduck`
- MCP clients that need a tool-friendly analytics surface
- `semduck ask` CLI for natural-language analytics flows

## Start Here

- [Quickstart](docs/getting-started/quickstart.md)
- [How Semduck Works](docs/guides/how-semduck-works.md)
- [Choosing An Interface](docs/guides/choosing-an-interface.md)
- [Contributing](CONTRIBUTING.md)
- [Package README](packages/semduck)
- [Docs Site Source](docs)

## Packages

- [`packages/semduck`](packages/semduck): Python runtime, CLI, compiler, registry, MCP server, ask workflow, and DuckDB interface
- [`packages/dbt-semduck`](packages/dbt-semduck): dbt macros and materializations for semantic view registration and query compilation

## Repo Layout

- [`docs`](docs): GitHub Pages documentation site
- [`examples/dbt_example`](examples/dbt_example): end-to-end `dbt-duckdb` example project
- [`integration_tests`](integration_tests): end-to-end dbt integration coverage
- [`examples/test_fixtures`](examples/test_fixtures): fixture projects used by automated tests

## Compatibility Baseline

- Python: `3.11` through `3.13`
- DuckDB: `1.4+`
- dbt interface: `dbt-duckdb` `1.9.x` or newer within the supported range
