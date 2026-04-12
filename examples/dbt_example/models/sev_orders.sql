{{ config(materialized='semduck_semantic') }}

create semantic view orders as
  -- ai_context (
  --   concept recent (
  --     concept_kind modifier
  --     phrases ('recent', 'recently')
  --     default_window '30 days'
  --     time_dimension order_date
  --   )
  -- )

table {{ ref('fct_orders') }} as orders
  primary key (order_id)
  dimensions (
    order_id as order_id,
    customer_id as customer_id,
    order_date as order_date type date 
      -- ai_context (
      --   concept order_date (
      --     phrases ('order date', 'purchase date')
      --   )
      -- )
  )
  
  facts (
    order_total as order_total type double
  )

  metrics (
    sum(order_total) as total_revenue,
      -- ai_context (
      --   concept total_revenue (
      --     phrases ('revenue', 'total revenue')
      --     preferred true
      --   )
      -- ),
    count(order_id) as order_count,
      -- ai_context (
      --   concept order_count (
      --     phrases ('order count', 'orders')
      --   )
      -- ),
    total_revenue / order_count as average_order_value
  )

table {{ ref('dim_customers') }} as customers
  primary key (customer_id)
  dimensions (
    customer_name as customer_name 
      -- ai_context (
      --   concept customer_name (
      --     phrases ('customer name', 'customer')
      --   )
      -- )
  )

join orders_to_customers:
  left_table orders
  right_table customers
  join_type left
  on LEFT_TABLE.customer_id = RIGHT_TABLE.customer_id;
