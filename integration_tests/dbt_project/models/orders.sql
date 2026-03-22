select
  order_id,
  customer_id,
  region,
  revenue
from {{ ref('orders_seed') }}
