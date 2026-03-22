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
