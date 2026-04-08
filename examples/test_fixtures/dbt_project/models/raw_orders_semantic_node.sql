-- depends_on: {{ source('raw', 'orders_seed') }}

{{ config(materialized='semduck_semantic') }}

create semantic view raw_orders_semantic as
table {{ source('raw', 'orders_seed') }} as raw_orders
  dimensions (
    region as region
  )
  metrics (
    sum(revenue) as total_revenue
  );
