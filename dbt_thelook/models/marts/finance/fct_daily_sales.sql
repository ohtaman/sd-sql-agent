select
    date(item_created_at) as sales_date,
    sum(sale_price) as revenue,
    count(distinct order_id) as order_count,
    count(*) as item_count
from {{ ref('int_order_items_with_products') }}
where item_status in ('Shipped', 'Complete')
group by sales_date
