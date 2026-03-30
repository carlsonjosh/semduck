-- depends_on: {{ source('raw', 'orders_seed') }}

{{ config(materialized='semduck_semantic') }}

create semantic view raw_orders_semantic as
table raw_orders as {{ source('raw', 'orders_seed') }}
  dimensions (
    region as region
  )
  metrics (
    sum(revenue) as total_revenue
  );
