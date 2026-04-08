{{ config(materialized='semduck_semantic') }}

create semantic view orders as
table {{ ref('fct_orders') }} as orders
  primary key (order_id)
  dimensions (
    order_id as order_id,
    customer_id as customer_id,
    order_date as order_date type date
  )
  facts (
    order_total as order_total type double
  )
  metrics (
    sum(order_total) as total_revenue,
    count(order_id) as order_count,
    total_revenue / order_count as average_order_value
  )

table {{ ref('dim_customers') }} as customers
  primary key (customer_id)
  dimensions (
    customer_name as customer_name
  )

join orders_to_customers:
  left_table orders
  right_table customers
  join_type left
  on LEFT_TABLE.customer_id = RIGHT_TABLE.customer_id;
