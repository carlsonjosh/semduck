# semduck

Portable semantic view runtime for DuckDB, implemented in Python.

Supported baseline:

- Python `3.11` to `3.12`
- DuckDB `1.4+`
- `dbt-duckdb` `1.10.x` for the optional dbt plugin path

## Install

```bash
pip install semduck
```

Install the dbt integration dependency only if you are registering the DuckDB plugin in a `dbt-duckdb` project:

```bash
pip install "semduck[dbt]"
```

## Supported Patterns

- Standalone Python package and CLI:
  - YAML semantic specs
  - semantic DDL
- dbt integration through `dbt-semduck`:
  - inline semantic DDL only

YAML support is still available in the Python package and CLI. The dbt integration deliberately uses DDL instead of YAML-in-dbt so `semduck` stays dbt-agnostic.

## Quickstart

Start by initializing a registry. This creates a semantic schema and several supporting tables in 
the duckdb database you provide. 

```bash
semduck init --db demo.duckdb
```

Load a semantic definition from YAML:

```bash
semduck load --db demo.duckdb --file orders_semantic.yaml
semduck compile --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

Load a semantic definition from DDL:

```bash
semduck load --db demo.duckdb --format ddl --file path/to/orders_semantic.sql
semduck query --db demo.duckdb --request "orders_semantic dimensions region metrics total_revenue"
```

The CLI accepts `--format auto|yaml|ddl` for `check` and `load`. In `auto` mode it uses the file extension or the first non-empty line to infer the format.

Configure an Ollama-backed ask provider and run the ask CLI:

```bash
semduck ask \
  --db examples/dbt_example/jaffle_shop.duckdb \
  --config packages/semduck/examples/ask_ollama_config.yaml \
  --llm-log-dir .semduck/llm-logs \
  --question "What is total revenue by customer name?" \
  --sql
```

Configure an OpenAI-compatible local server and run the ask CLI:

```bash
semduck ask \
  --db examples/dbt_example/jaffle_shop.duckdb \
  --config packages/semduck/examples/ask_openai_compatible_config.yaml \
  --llm-log-dir .semduck/llm-logs \
  --question "What is total revenue by customer name?" \
  --sql
```

Set `llm.log_dir` in the config file to enable persistent trace logging by default, or use `--llm-log-dir` to override it per run. Pass `--no-llm-log` to disable logging even when the config file specifies a directory.

`semduck ask` now uses a planner stage to build the semantic request and, when `--summary` is requested, a separate summary stage to explain the executed rows. Advanced users can configure different models for those jobs with `llm.tasks.ask_plan` and `llm.tasks.ask_summary`. If task-specific config is used, the summary task only needs to be configured when summary output is requested.

During `semduck ask`, the CLI now prints one-line stage updates such as planning, compile, execution, and summarization to `stderr`. Final results remain on `stdout`, so JSON output stays machine-readable.

Start the semduck MCP server over `stdio`:

```bash
semduck mcp --db examples/dbt_example/jaffle_shop.duckdb
```

## Authoring Formats

### YAML

The standalone YAML shape is still supported for Python and CLI usage.

Minimal valid YAML:

```yaml
name: sample
tables:
  - name: orders
    base_table:
      table: orders_base
    dimensions:
      - name: region
        expr: region
    metrics:
      - name: order_count
        metric_type: count
        expr: order_id
```

More complete example: [`examples/orders_semantic.yaml`](https://github.com/carlsonjosh/semduck/blob/main/packages/semduck/examples/orders_semantic.yaml)

Validation rules enforced by the loader:

- top-level YAML must be a mapping
- semantic view `name` is required
- `tables` must be a non-empty list
- every table needs a unique `name`
- every table needs `base_table.table`
- semantic object names must be unique within a table across `dimensions`, `time_dimensions`, `facts`, and `metrics`
- `dimensions`, `time_dimensions`, and `facts` entries require `name` and `expr`
- `metrics` entries require `name`, `metric_type`, and `expr`
- joins must reference declared tables and require `name`, `left_table`, `right_table`, `join_type`, and `join_expr`

### DDL

Semantic DDL is supported in the Python package, CLI, and dbt integration.

Example:

```sql
create semantic view orders_semantic as
table orders as main.orders
  primary key (order_id)
  dimensions (
    region as region
  )
  metrics (
    sum(revenue) as total_revenue,
    count(order_id) as order_count
  );
```

Repo examples:

- Standalone / parser shape: [`examples/dbt_jaffle_shop/models/sev_orders.sql`](https://github.com/carlsonjosh/semduck/blob/main/examples/dbt_jaffle_shop/models/sev_orders.sql)
- dbt materialization usage: [`packages/dbt-semduck/README.md`](https://github.com/carlsonjosh/semduck/blob/main/packages/dbt-semduck/README.md)

## Python API

The package exposes both YAML and DDL loaders:

```python
import duckdb
from semduck import compile_request_sql, init_registry, load_semantic_ddl, load_semantic_yaml

conn = duckdb.connect("demo.duckdb")
init_registry(conn)

load_semantic_yaml(conn, """
name: sample
tables:
  - name: orders
    base_table:
      table: orders
    dimensions:
      - name: region
        expr: region
    metrics:
      - name: order_count
        metric_type: count
        expr: order_id
""")

load_semantic_ddl(conn, """
create semantic view replacement_sample as
table orders as main.orders
  dimensions (
    region as region
  )
  metrics (
    count(order_id) as order_count
  );
""")

sql = compile_request_sql(conn, "replacement_sample dimensions region metrics order_count")
print(sql)
```

Relevant API entry points:

- `init_registry(conn)`
- `load_semantic_yaml(conn, yaml_text)`
- `load_semantic_ddl(conn, ddl_text)`
- `load_semantic_yaml_file(conn, path)`
- `load_semantic_ddl_file(conn, path)`
- `compile_request_sql(conn, request)`
- `execute_request(conn, request)`

## dbt Boundary

`semduck` keeps dbt-specific behavior in the `dbt-semduck` package.

- Supported in dbt: inline semantic DDL compiled by dbt and then loaded into `semduck`
- Not supported in dbt: YAML specs containing unresolved `ref(...)` or `source(...)`

The design note for that boundary is in [`project/decisions/remove_yaml_in_dbt_support.md`](https://github.com/carlsonjosh/semduck/blob/main/project/decisions/remove_yaml_in_dbt_support.md).

## Repo Examples

- In-memory Python quickstart: [`examples/quickstart.py`](https://github.com/carlsonjosh/semduck/blob/main/packages/semduck/examples/quickstart.py)
- Query an existing database from Python: [`examples/query_existing_db.py`](https://github.com/carlsonjosh/semduck/blob/main/packages/semduck/examples/query_existing_db.py)
- Query an existing database from the CLI: [`examples/query_existing_db_cli.sh`](https://github.com/carlsonjosh/semduck/blob/main/packages/semduck/examples/query_existing_db_cli.sh)
- Register an Ollama provider config and use `semduck ask`: [`examples/ask_existing_db_cli.sh`](https://github.com/carlsonjosh/semduck/blob/main/packages/semduck/examples/ask_existing_db_cli.sh)
- Example Ollama provider config: [`examples/ask_ollama_config.yaml`](https://github.com/carlsonjosh/semduck/blob/main/packages/semduck/examples/ask_ollama_config.yaml)
- Example OpenAI-compatible local provider config: [`examples/ask_openai_compatible_config.yaml`](https://github.com/carlsonjosh/semduck/blob/main/packages/semduck/examples/ask_openai_compatible_config.yaml)
- Start the MCP server over stdio: [`examples/mcp_server_stdio.sh`](https://github.com/carlsonjosh/semduck/blob/main/packages/semduck/examples/mcp_server_stdio.sh)
- Example MCP client config: [`examples/mcp_client_config.json`](https://github.com/carlsonjosh/semduck/blob/main/packages/semduck/examples/mcp_client_config.json)
- MCP startup and client connection guide: [`examples/mcp_connection_guide.md`](https://github.com/carlsonjosh/semduck/blob/main/packages/semduck/examples/mcp_connection_guide.md)
- End-to-end dbt example: [`examples/dbt_example`](https://github.com/carlsonjosh/semduck/tree/main/examples/dbt_example)

## Development

```bash
uv sync
uv run pytest
uv run tox
```
