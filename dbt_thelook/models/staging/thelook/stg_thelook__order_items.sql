
-- 注文明細のステージングモデル
-- ソースと1:1対応
-- カラム名を分かりやすく変更

select
    id as order_item_id,
    order_id,
    user_id,
    product_id,
    inventory_item_id,
    status as item_status,
    created_at as item_created_at,
    shipped_at,
    delivered_at,
    returned_at,
    sale_price

from {{ source('thelook', 'order_items') }}
