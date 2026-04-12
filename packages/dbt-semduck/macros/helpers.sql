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

{% macro semduck__ddl_metadata_payload(model) -%}
  {% if not execute %}
    {{ return('{}') }}
  {% endif %}
  {% set payload = {'meta': model.meta or {}, 'config_meta': model.config.get('meta', {}) or {}, 'columns': {}} %}
  {% for column_name, column in model.columns.items() %}
    {% do payload['columns'].update({
      column_name: {
        'meta': column.meta or {}
      }
    }) %}
  {% endfor %}
  {{ return(tojson(payload)) }}
{%- endmacro %}
