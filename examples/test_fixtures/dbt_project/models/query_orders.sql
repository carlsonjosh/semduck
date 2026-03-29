select *
from {{ dbt_semduck.from_query(
    ref('orders_semantic_node'),
    'dimensions region metrics total_revenue'
) }}
