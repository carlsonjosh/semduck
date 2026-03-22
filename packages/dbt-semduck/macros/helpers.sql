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

{% macro semduck__path_exists(path) -%}
  {% set sql = "select semduck_path_exists(" ~ dbt_semduck.semduck__sql_literal(path) ~ ") as exists_flag" %}
  {{ return(dbt_semduck.semduck__scalar(sql)) }}
{%- endmacro %}

{% macro semduck__spec_path(configured_path) -%}
  {% if configured_path is none %}
    {% do exceptions.raise_compiler_error("semduck_spec config is required when semduck_semantic is not using inline DDL") %}
  {% endif %}
  {{ return(configured_path) }}
{%- endmacro %}

{% macro semduck__relation_map_json() -%}
  {% set relation_map = {} %}

  {% for node in graph.nodes.values() %}
    {% if node.resource_type in ['model', 'seed', 'snapshot'] %}
      {% set relation = {} %}
      {% if node.database %}
        {% do relation.update({'database': node.database}) %}
      {% endif %}
      {% if node.schema %}
        {% do relation.update({'schema': node.schema}) %}
      {% endif %}
      {% do relation.update({'table': node.alias}) %}
      {% do relation_map.update({'ref:' ~ node.name: relation}) %}
    {% endif %}
  {% endfor %}

  {% for source_node in graph.sources.values() %}
    {% set relation = {} %}
    {% if source_node.database %}
      {% do relation.update({'database': source_node.database}) %}
    {% endif %}
    {% if source_node.schema %}
      {% do relation.update({'schema': source_node.schema}) %}
    {% endif %}
    {% do relation.update({'table': source_node.identifier}) %}
    {% do relation_map.update({'source:' ~ source_node.source_name ~ '.' ~ source_node.name: relation}) %}
  {% endfor %}

  {{ return(tojson(relation_map)) }}
{%- endmacro %}
