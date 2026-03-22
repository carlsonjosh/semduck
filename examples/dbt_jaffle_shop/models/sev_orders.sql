{{ config(materialized='semduck_semantic') }}

create semantic view orders_semantic as
table orders as {{ ref('fct_orders') }}
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
    total_revenue as sum(order_total),
    order_count as count(order_id)
  )

table customers as {{ ref('dim_customers') }}
  primary key (customer_id)
  dimensions (
    customer_name as customer_name
  )

join orders_to_customers:
  left_table orders
  right_table customers
  join_type left
  on LEFT_TABLE.customer_id = RIGHT_TABLE.customer_id;
