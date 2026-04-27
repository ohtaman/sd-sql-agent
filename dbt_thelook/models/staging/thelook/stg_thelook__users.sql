
-- ユーザーマスタのステージングモデル
-- ソースと1:1対応
-- カラム名を分かりやすく変更

select
    id as user_id,
    first_name,
    last_name,
    email,
    age,
    gender,
    state,
    country,
    created_at

from {{ source('thelook', 'users') }}
