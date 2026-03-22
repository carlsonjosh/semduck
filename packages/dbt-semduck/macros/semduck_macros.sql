{% macro semduck_check(path) -%}
  {% if not execute %}
    {{ return('') }}
  {% endif %}
  {% if not dbt_semduck.semduck__path_exists(path) %}
    {{ return('') }}
  {% endif %}
  {% set relation_map_json = dbt_semduck.semduck__relation_map_json() %}
  {% set sql = "select semduck_check_yaml_file(" ~ dbt_semduck.semduck__sql_literal(path) ~ ", " ~ dbt_semduck.semduck__sql_literal(relation_map_json) ~ ") as status" %}
  {% do run_query(sql) %}
  {{ return('') }}
{%- endmacro %}

{% macro semduck_load(path) -%}
  {% if not execute %}
    {{ return(none) }}
  {% endif %}
  {% if not dbt_semduck.semduck__path_exists(path) %}
    {{ return(none) }}
  {% endif %}
  {% set relation_map_json = dbt_semduck.semduck__relation_map_json() %}
  {% set check_sql = "select semduck_check_yaml_file(" ~ dbt_semduck.semduck__sql_literal(path) ~ ", " ~ dbt_semduck.semduck__sql_literal(relation_map_json) ~ ") as status" %}
  {% set load_sql = "select semduck_load_yaml_file(" ~ dbt_semduck.semduck__sql_literal(path) ~ ", " ~ dbt_semduck.semduck__sql_literal(relation_map_json) ~ ") as status" %}
  {% do run_query(check_sql) %}
  {% set status = dbt_semduck.semduck__scalar(load_sql) %}
  {{ return(status.split('view_name=')[-1]) }}
{%- endmacro %}

{% macro semduck_query(request) -%}
  {% if not execute %}
    {{ return("select 1 where 1 = 0") }}
  {% endif %}
  {% set sql = "select semduck_compile(" ~ dbt_semduck.semduck__sql_literal(request) ~ ") as compiled_sql" %}
  {% set compiled = dbt_semduck.semduck__scalar(sql) %}
  {{ return(compiled.rstrip().rstrip(';')) }}
{%- endmacro %}

{% macro semduck_load_ddl(ddl_text) -%}
  {% if not execute %}
    {{ return(none) }}
  {% endif %}
  {% set check_sql = "select semduck_check_ddl(" ~ dbt_semduck.semduck__sql_literal(ddl_text) ~ ") as status" %}
  {% set load_sql = "select semduck_load_ddl(" ~ dbt_semduck.semduck__sql_literal(ddl_text) ~ ") as status" %}
  {% do run_query(check_sql) %}
  {% set status = dbt_semduck.semduck__scalar(load_sql) %}
  {{ return(status.split('view_name=')[-1]) }}
{%- endmacro %}
