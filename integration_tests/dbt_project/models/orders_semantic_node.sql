-- depends_on: {{ ref('orders') }}

{{ config(
    materialized='semduck_semantic',
    semduck_spec='semantic_specs/custom_orders_definition.yml'
) }}

select 'orders_semantic' as semantic_view_name
