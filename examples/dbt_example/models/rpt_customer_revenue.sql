select *
from {{ dbt_semduck.from_query(
    ref('sev_orders'),
    'dimensions customer_name
     metrics total_revenue, total_revenue / 1000 as revenue_in_thousands'
) }}
