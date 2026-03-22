{% materialization semduck_semantic, default %}
  {%- set configured_path = config.get('semduck_spec') -%}
  {%- if configured_path is not none -%}
    {%- set spec_path = dbt_semduck.semduck__spec_path(configured_path) -%}
    {%- set loaded_name = dbt_semduck.semduck_load(spec_path) -%}
    {%- set load_source = spec_path -%}
  {%- else -%}
    {%- set loaded_name = dbt_semduck.semduck_load_ddl(compiled_code) -%}
    {%- set load_source = 'inline ddl' -%}
  {%- endif -%}
  {%- set existing_relation = load_cached_relation(this) -%}
  {%- set target_relation = this.incorporate(type='view') -%}
  {%- set intermediate_relation = make_intermediate_relation(target_relation) -%}
  {%- set preexisting_intermediate_relation = load_cached_relation(intermediate_relation) -%}
  {%- set backup_relation_type = 'view' if existing_relation is none else existing_relation.type -%}
  {%- set backup_relation = make_backup_relation(target_relation, backup_relation_type) -%}
  {%- set preexisting_backup_relation = load_cached_relation(backup_relation) -%}
  {% set grant_config = config.get('grants') %}

  {{ drop_relation_if_exists(preexisting_intermediate_relation) }}
  {{ drop_relation_if_exists(preexisting_backup_relation) }}

  {{ run_hooks(pre_hooks, inside_transaction=False) }}
  {{ run_hooks(pre_hooks, inside_transaction=True) }}

  {% call statement('main') -%}
    {{ get_create_view_as_sql(intermediate_relation, "select '" ~ loaded_name ~ "' as semantic_view_name, current_timestamp as loaded_at") }}
  {%- endcall %}

  {% if existing_relation is not none %}
    {% set existing_relation = load_cached_relation(existing_relation) %}
    {% if existing_relation is not none %}
      {{ adapter.rename_relation(existing_relation, backup_relation) }}
    {% endif %}
  {% endif %}

  {{ adapter.rename_relation(intermediate_relation, target_relation) }}

  {% set should_revoke = should_revoke(existing_relation, full_refresh_mode=True) %}
  {% do apply_grants(target_relation, grant_config, should_revoke=should_revoke) %}
  {% do persist_docs(target_relation, model) %}

  {{ run_hooks(post_hooks, inside_transaction=True) }}
  {{ adapter.commit() }}
  {{ drop_relation_if_exists(backup_relation) }}
  {{ run_hooks(post_hooks, inside_transaction=False) }}

  {{ log("loaded semduck definition from " ~ load_source ~ " as " ~ loaded_name, info=True) }}
  {{ return({'relations': [target_relation]}) }}
{% endmaterialization %}
