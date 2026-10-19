select
    entity_id,
    account_id,
    name                  as account_name,
    fully_qualified_name,
    account_type,
    account_sub_type,
    classification,
    currency              as account_currency,
    active                as is_active,
    classification in ('Revenue', 'Expense') as is_pnl_account,
    -- QuickBooks classification decides how an account affects net income
    case classification when 'Revenue' then 1 when 'Expense' then -1 end as source_sign,
    try_cast(last_updated_at as timestamptz) as source_updated_at,
    _loaded_at
from {{ source('raw', 'qbo_accounts') }}
