{% macro semduck__sql_literal(value) -%}
  '{{ value | replace("'", "''") }}'
{%- endmacro %}

{% macro semduck__scalar(sql) -%}
  {% if not execute %}
    {{ return(none) }}
  {% endif %}
  {% set result = run_query(sql) %}
  {% if result is none %}
    {{ return(none) }}
  {% endif %}
  {{ return(result.columns[0].values()[0]) }}
{%- endmacro %}
