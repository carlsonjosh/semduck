select
  order_id,
  customer_id,
  cast(order_date as date) as order_date,
  cast(order_total as double) as order_total
from {{ ref('orders') }}
