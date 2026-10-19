-- RECONCILIATION: for every account, the sum of our monthly rows must equal the
-- total QuickBooks reports for the same range (a separate API call).
-- Catches incremental-sync bugs, e.g. an edit outside the lookback window.
with modeled as (
    select entity_id, account_id, sum(amount_local) as amount
    from {{ ref('stg_qbo__pnl_monthly') }}
    group by 1, 2
),
source_totals as (
    select entity_id, account_id, sum(total_amount) as amount
    from {{ source('raw', 'qbo_pnl_period_totals') }}
    group by 1, 2
)
select
    coalesce(m.entity_id, s.entity_id)   as entity_id,
    coalesce(m.account_id, s.account_id) as account_id,
    m.amount as modeled_amount,
    s.amount as quickbooks_amount,
    round(coalesce(m.amount, 0) - coalesce(s.amount, 0), 2) as difference
from modeled m
full outer join source_totals s on m.entity_id = s.entity_id and m.account_id = s.account_id
where abs(coalesce(m.amount, 0) - coalesce(s.amount, 0)) > 0.01
