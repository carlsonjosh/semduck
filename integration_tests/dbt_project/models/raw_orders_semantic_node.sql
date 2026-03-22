-- depends_on: {{ source('raw', 'orders_seed') }}

{{ config(
    materialized='semduck_semantic',
    semduck_spec='semantic_configs/raw_orders_metrics.yaml'
) }}

select 'raw_orders_semantic' as semantic_view_name
