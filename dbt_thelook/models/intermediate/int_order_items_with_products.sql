select
    oi.order_item_id,
    oi.order_id,
    oi.product_id,
    p.product_name,
    p.category,
    p.brand,
    oi.item_status,
    oi.sale_price,
    oi.item_created_at,
    p.department,
    p.product_cost,
    p.retail_price
from {{ ref('stg_thelook__order_items') }} oi
left join {{ ref('stg_thelook__products') }} p
    on oi.product_id = p.product_id
