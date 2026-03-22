-- depends_on: {{ ref('orders') }}

select *
from (
  {{ dbt_semduck.semduck_query("orders_semantic dimensions region metrics total_revenue") }}
)
