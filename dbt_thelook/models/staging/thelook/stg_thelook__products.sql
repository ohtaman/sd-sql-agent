
-- 商品マスタのステージングモデル
-- ソースと1:1対応
-- カラム名を分かりやすく変更

select
    id as product_id,
    name as product_name,
    cost as product_cost,
    retail_price,
    category,
    brand,
    department,
    sku,
    distribution_center_id

from {{ source('thelook', 'products') }}
