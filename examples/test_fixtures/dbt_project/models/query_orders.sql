select *
from (
  {{ dbt_semduck.query(
      ref('orders_semantic_node'),
      'dimensions region metrics total_revenue'
  ) }}
)
