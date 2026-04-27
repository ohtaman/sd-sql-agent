
-- 商品別粗利ファクト
-- 商品ごとの累計売上・原価・粗利を算出
-- 商品パフォーマンス分析に使用

with order_items_with_products as (
    select * from {{ ref('int_order_items_with_products') }}
),

product_metrics as (
    select
        product_id,
        product_name,
        category,
        brand,
        department,
        sum(sale_price) as total_revenue,
        sum(product_cost) as total_cost,
        sum(sale_price - product_cost) as total_margin,
        count(*) as units_sold
    from order_items_with_products
    where item_status not in ('Cancelled', 'Returned')  -- 確定売上のみ
    group by product_id, product_name, category, brand, department
)

select
    *,
    case
        when total_revenue > 0
        then round(total_margin / total_revenue * 100, 2)
        else 0
    end as margin_rate  -- 粗利率（%）

from product_metrics
