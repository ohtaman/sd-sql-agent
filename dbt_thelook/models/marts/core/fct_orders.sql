
-- 注文ファクト
-- 注文単位の分析に使用
-- 注文金額はorder_itemsから集計して算出

with orders as (
    select * from {{ ref('stg_thelook__orders') }}
),

order_items as (
    select * from {{ ref('stg_thelook__order_items') }}
),

order_totals as (
    -- 注文ごとの合計金額と明細数を計算
    select
        order_id,
        sum(sale_price) as order_total,
        count(*) as item_count
    from order_items
    group by order_id
)

select
    orders.order_id,
    orders.user_id,
    orders.order_status,
    coalesce(order_totals.order_total, 0) as order_total,
    coalesce(order_totals.item_count, 0) as item_count,
    orders.created_at,
    orders.shipped_at

from orders
left join order_totals
    on orders.order_id = order_totals.order_id
