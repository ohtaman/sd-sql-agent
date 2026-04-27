
-- 注文明細ファクト
-- 発送基準で計上（Shipped, Completeのみ）
-- Processing（未発送）、Cancelled、Returnedは除外

with order_items_with_products as (
    select * from {{ ref('int_order_items_with_products') }}
)

select
    order_item_id,
    order_id,
    product_id,
    product_name,
    category,
    brand,
    department,
    sale_price,
    product_cost,
    sale_price - product_cost as margin,  -- 粗利を計算
    item_status,
    item_created_at as created_at

from order_items_with_products
where item_status in ('Shipped', 'Complete')  -- 発送基準
