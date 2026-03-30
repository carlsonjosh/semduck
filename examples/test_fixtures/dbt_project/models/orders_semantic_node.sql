-- depends_on: {{ ref('orders') }}

{{ config(materialized='semduck_semantic') }}

create semantic view orders_semantic as
table orders as {{ ref('orders') }}
  dimensions (
    region as region type varchar
  )
  metrics (
    sum(revenue) as total_revenue
  );
