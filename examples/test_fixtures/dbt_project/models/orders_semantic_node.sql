-- depends_on: {{ ref('orders') }}

{{ config(materialized='semduck_semantic') }}

create semantic view orders_semantic as
table {{ ref('orders') }} as orders
  dimensions (
    region as region type varchar
  )
  metrics (
    sum(revenue) as total_revenue
  );
