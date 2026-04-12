{% macro semduck_query(request) -%}
  {% if not execute %}
    {{ return("select 1 where 1 = 0") }}
  {% endif %}
  {% set sql = "select semduck_compile(" ~ dbt_semduck.semduck__sql_literal(request) ~ ") as compiled_sql" %}
  {% set compiled = dbt_semduck.semduck__scalar(sql) %}
  {{ return(compiled.rstrip().rstrip(';')) }}
{%- endmacro %}

{% macro query(semantic_node_relation, request_suffix) -%}
  {% if not execute %}
    {{ return("select 1 where 1 = 0") }}
  {% endif %}

  {% set semantic_node_sql = semantic_node_relation.render() if semantic_node_relation is not string else semantic_node_relation %}
  {% set lookup_sql = "select semantic_view_name from " ~ semantic_node_sql %}
  {% set semantic_view_name = dbt_semduck.semduck__scalar(lookup_sql) %}

  {% if semantic_view_name is none %}
    {% do exceptions.raise_compiler_error("semantic node relation did not return a semantic_view_name: " ~ semantic_node_sql) %}
  {% endif %}

  {% set request = semantic_view_name ~ " " ~ request_suffix.strip() %}
  {{ return(dbt_semduck.semduck_query(request)) }}
{%- endmacro %}

{% macro from_query(semantic_node_relation, request_suffix, alias='semduck_query') -%}
  {% if not execute %}
    {{ return("(select 1 where 1 = 0) " ~ alias) }}
  {% endif %}

  {% set compiled = dbt_semduck.query(semantic_node_relation, request_suffix) %}
  {{ return("(" ~ compiled ~ ") " ~ alias) }}
{%- endmacro %}

{% macro semduck_load_ddl(ddl_text, dbt_metadata_json=none) -%}
  {% if not execute %}
    {{ return(none) }}
  {% endif %}
  {% if dbt_metadata_json is none %}
    {% set check_sql = "select semduck_check_ddl(" ~ dbt_semduck.semduck__sql_literal(ddl_text) ~ ") as status" %}
    {% set load_sql = "select semduck_load_ddl(" ~ dbt_semduck.semduck__sql_literal(ddl_text) ~ ") as status" %}
  {% else %}
    {% set check_sql = "select semduck_check_ddl_with_dbt_meta(" ~ dbt_semduck.semduck__sql_literal(ddl_text) ~ ", " ~ dbt_semduck.semduck__sql_literal(dbt_metadata_json) ~ ") as status" %}
    {% set load_sql = "select semduck_load_ddl_with_dbt_meta(" ~ dbt_semduck.semduck__sql_literal(ddl_text) ~ ", " ~ dbt_semduck.semduck__sql_literal(dbt_metadata_json) ~ ") as status" %}
  {% endif %}
  {% do run_query(check_sql) %}
  {% set status = dbt_semduck.semduck__scalar(load_sql) %}
  {{ return(status.split('view_name=')[-1]) }}
{%- endmacro %}
