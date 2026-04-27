
-- ユーザーディメンション
-- 分析用にわかりやすい形式に整形

with users as (
    select * from {{ ref('stg_thelook__users') }}
)

select
    user_id,
    concat(first_name, ' ', last_name) as full_name,
    email,
    age,
    gender,
    concat(state, ', ', country) as location,
    created_at

from users
