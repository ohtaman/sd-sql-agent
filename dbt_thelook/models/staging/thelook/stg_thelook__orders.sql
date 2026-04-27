select
    order_id,
    user_id,
    status as order_status,
    created_at,
    returned_at,
    shipped_at,
    num_of_item

from {{ source('thelook', 'orders') }}  -- sources.ymlで定義したソースを参照
