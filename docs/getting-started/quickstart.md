# Quickstart

This walkthrough starts from scratch with a public weather dataset and then shows the same Semduck flow through both the CLI and the Python API.

It uses Vega Datasets `weather.csv`, which contains daily weather observations for Seattle and New York.
Source: [weather.csv](https://cdn.jsdelivr.net/npm/vega-datasets@3.2.1/data/weather.csv), [dataset metadata](https://vega.github.io/vega-datasets/datapackage.html)

## 1. Install And Download The Dataset

```bash
pip install semduck
curl -L https://cdn.jsdelivr.net/npm/vega-datasets@3.2.1/data/weather.csv -o weather.csv
```

## 2. Create A DuckDB Database

Use DuckDB through Python to create a local database file and load the CSV into a table named `weather_raw`:

```python
import duckdb

conn = duckdb.connect("weather.duckdb")
conn.execute(
    """
    create or replace table weather_raw as
    select *
    from read_csv(?, auto_detect=true)
    """,
    ["weather.csv"],
)
conn.close()
```

## 3. Load The Semantic View

This repository includes a ready-to-use semantic definition at `packages/semduck/examples/weather_semantic.yaml`.

=== "CLI"

    ```bash
    semduck init --db weather.duckdb
    semduck load --db weather.duckdb --file packages/semduck/examples/weather_semantic.yaml
    ```

=== "Python"

    ```python
    import duckdb
    from semduck import init_registry, load_semantic_yaml_file

    conn = duckdb.connect("weather.duckdb")
    init_registry(conn)
    load_semantic_yaml_file(conn, "packages/semduck/examples/weather_semantic.yaml")
    conn.close()
    ```

The CLI supports `--format auto|yaml|ddl` for semantic definition files. In `auto` mode, Semduck infers the format from the file extension or the first non-empty line.

## 4. Compile A Request

=== "CLI"

    ```bash
    semduck compile --db weather.duckdb --request "weather dimensions location, weather metrics day_count, avg_temp_max"
    ```

=== "Python"

    ```python
    import duckdb
    from semduck import compile_request_sql

    conn = duckdb.connect("weather.duckdb")
    sql = compile_request_sql(
        conn,
        "weather dimensions location, weather metrics day_count, avg_temp_max",
    )
    print(sql)
    conn.close()
    ```

## 5. Execute A Request

=== "CLI"

    ```bash
    semduck query --db weather.duckdb --request "weather dimensions location, weather metrics day_count, avg_temp_max"
    ```

=== "Python"

    ```python
    import duckdb
    from semduck import execute_request

    conn = duckdb.connect("weather.duckdb")
    result = execute_request(
        conn,
        "weather dimensions location, weather metrics day_count, avg_temp_max",
    )
    print(result.fetchall())
    conn.close()
    ```

## 6. Try A Derived Time Dimension

Once the basic query works, try a derived dimension:

=== "CLI"

    ```bash
    semduck query --db weather.duckdb --request "weather dimensions date_trunc('month', date) as month, location metrics total_precipitation"
    ```

=== "Python"

    ```python
    import duckdb
    from semduck import execute_request

    conn = duckdb.connect("weather.duckdb")
    result = execute_request(
        conn,
        "weather dimensions date_trunc('month', date) as month, location metrics total_precipitation",
    )
    print(result.fetchall())
    conn.close()
    ```

## 7. Use The Larger Example Project

The repository also includes a richer dbt-backed example in `examples/dbt_example`.

- Standalone Python example against the checked-in dbt example database: `packages/semduck/examples/query_existing_db.py`
- CLI wrapper around that database: `packages/semduck/examples/query_existing_db_cli.sh`
- End-to-end dbt project: `examples/dbt_example`

## Next Steps

- Learn the [request language](../guides/request-language.md).
- Choose between [YAML and DDL definitions](../guides/semantic-definitions.md).
- Move to [dbt](../guides/dbt.md), [MCP](../guides/mcp.md), or [ask](../guides/ask.md) if you need those integrations.
