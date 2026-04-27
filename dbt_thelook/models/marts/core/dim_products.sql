
-- 商品ディメンション
-- 商品分析に必要な情報を整形

with products as (
    select * from {{ ref('stg_thelook__products') }}
)

select
    product_id,
    product_name,
    category,
    brand,
    department,
    product_cost,
    retail_price,
    sku

from products
