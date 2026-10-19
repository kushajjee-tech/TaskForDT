-- RECONCILIATION: our net income per entity and month (from QuickBooks lines only,
-- in local currency) must equal QuickBooks' own Net Income.
with modeled as (
    select entity_id, period, sum(signed_local) as net_income
    from {{ ref('int_gl_usd') }}
    where line_source = 'quickbooks'
    group by 1, 2
)
select s.entity_id, s.period, m.net_income as modeled, s.net_income as quickbooks,
       round(coalesce(m.net_income, 0) - s.net_income, 2) as difference
from {{ source('raw', 'qbo_pnl_net_income') }} s
left join modeled m on m.entity_id = s.entity_id and m.period = s.period
where abs(coalesce(m.net_income, 0) - s.net_income) > 0.01
