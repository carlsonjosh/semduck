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

{% macro semduck_on_run_start() -%}
  {% if not execute %}
    {{ return('') }}
  {% endif %}

  {% set loaded_names = [] %}
  {% for node in graph.nodes.values() %}
    {% if node.resource_type == 'model' and node.package_name == project_name and node.original_file_path.endswith('.sql') %}
      {% set semantic_rel_path = node.original_file_path[:-4] ~ '.semantic.yml' %}
      {% if dbt_semduck.semduck__path_exists(semantic_rel_path) %}
        {% set loaded_name = dbt_semduck.semduck_load(semantic_rel_path) %}
        {% if loaded_name in loaded_names %}
          {% do exceptions.raise_compiler_error(
            "duplicate semantic view name loaded during run: " ~ loaded_name
          ) %}
        {% endif %}
        {% do loaded_names.append(loaded_name) %}
      {% endif %}
    {% endif %}
  {% endfor %}

  {{ return('') }}
{%- endmacro %}
