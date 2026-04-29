# Quickstart

This walkthrough starts from scratch with a public weather dataset and then shows the same Semduck flow through both the CLI and the Python API.

If you are using `dbt-duckdb`, skip this page and go to the [dbt interface guide](../interfaces/dbt.md). The dbt setup and query flow are different enough that they are documented separately.

It uses Vega Datasets `weather.csv`, which contains daily weather observations for Seattle and New York.
Source: [weather.csv](https://cdn.jsdelivr.net/npm/vega-datasets@3.2.1/data/weather.csv), [dataset metadata](https://vega.github.io/vega-datasets/datapackage.html)

## 1. Install And Download The Dataset

```bash
pip install semduck
curl -L https://cdn.jsdelivr.net/npm/vega-datasets@3.2.1/data/weather.csv -o weather.csv
```

If you prefer `uv`, install Semduck with:

```bash
uv add semduck
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

Semduck also needs its registry schema initialized in that same database before you load any semantic definitions.

=== "CLI"

    ```bash
    semduck init --db weather.duckdb
    ```

=== "Python"

    ```python
    import duckdb
    from semduck import init_registry

    conn = duckdb.connect("weather.duckdb")
    init_registry(conn)
    conn.close()
    ```

## 3. Define The Semantic View

You can define the same semantic view in either YAML or semantic DDL.

=== "YAML"

    Create a file named `weather_semantic.yaml` with:

    ```yaml
    name: weather
    description: Daily weather observations grouped by location and weather type
    tables:
      - name: weather
        base_table:
          table: weather_raw
        time_dimensions:
          - name: date
            expr: date
            data_type: date
        dimensions:
          - name: location
            expr: location
            data_type: varchar
          - name: weather
            expr: weather
            data_type: varchar
        facts:
          - name: precipitation
            expr: precipitation
            data_type: double
          - name: temp_max
            expr: temp_max
            data_type: double
          - name: temp_min
            expr: temp_min
            data_type: double
          - name: wind
            expr: wind
            data_type: double
        metrics:
          - name: day_count
            expr: count(*)
            description: Number of daily observations
          - name: avg_temp_max
            expr: avg(temp_max)
            description: Average maximum daily temperature
          - name: total_precipitation
            expr: sum(precipitation)
            description: Total precipitation
    ```

=== "DDL"

    Create a file named `weather_semantic.sql` with:

    ```sql
    create semantic view weather as
    table weather_raw as weather
      time_dimensions (
        date as date type date
      )
      dimensions (
        location as location type varchar,
        weather as weather type varchar
      )
      facts (
        precipitation as precipitation type double,
        temp_max as temp_max type double,
        temp_min as temp_min type double,
        wind as wind type double
      )
      metrics (
        count(*) as day_count description 'Number of daily observations',
        avg(temp_max) as avg_temp_max description 'Average maximum daily temperature',
        sum(precipitation) as total_precipitation description 'Total precipitation'
      );
    ```

The `weather_raw` table name in both versions comes from step 2.

## 4. Load The Semantic View

Load the definition file you created into the initialized database:

=== "YAML"

    === "CLI"

        ```bash
        semduck load --db weather.duckdb --file weather_semantic.yaml
        ```

    === "Python"

        ```python
        import duckdb
        from semduck import load_semantic_yaml_file

        conn = duckdb.connect("weather.duckdb")
        load_semantic_yaml_file(conn, "weather_semantic.yaml")
        conn.close()
        ```

=== "DDL"

    === "CLI"

        ```bash
        semduck load --db weather.duckdb --format ddl --file weather_semantic.sql
        ```

    === "Python"

        ```python
        import duckdb
        from semduck import load_semantic_ddl_file

        conn = duckdb.connect("weather.duckdb")
        load_semantic_ddl_file(conn, "weather_semantic.sql")
        conn.close()
        ```

The CLI supports `--format auto|yaml|ddl` for semantic definition files. In `auto` mode, Semduck infers the format from the file extension or the first non-empty line. The default mode is `auto`.

## 5. Compile A Request
The compile step allows you to identify if a given request is valid without executing the query in the database. 

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

## 6. Execute A Request
Use `query` to retrieve data.

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

## 7. Try A Derived Time Dimension

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

## 8. Use The Larger Example Project

The repository also includes a richer dbt-backed example in `examples/dbt_example`.

- Standalone Python example against the checked-in dbt example database: `packages/semduck/examples/query_existing_db.py`
- CLI wrapper around that database: `packages/semduck/examples/query_existing_db_cli.sh`
- End-to-end dbt project: `examples/dbt_example`

## Next Steps

- Learn the [request language](../guides/request-language.md).
- Choose between [YAML and DDL definitions](../guides/semantic-definitions.md).
- Move to the [dbt](../interfaces/dbt.md), [MCP](../interfaces/mcp.md), or [ask](../interfaces/ask.md) interfaces if you need those workflows.
