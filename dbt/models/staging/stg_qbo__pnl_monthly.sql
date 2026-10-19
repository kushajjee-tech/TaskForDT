select
    entity_id,
    account_id,
    account_name,
    report_section,
    period,
    amount as amount_local,
    _loaded_at
from {{ source('raw', 'qbo_pnl_monthly') }}
