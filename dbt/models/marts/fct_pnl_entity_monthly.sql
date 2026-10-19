-- P&L by entity, month and standard category, in local currency and USD.
-- Includes intercompany lines (each entity's own books).
select
    entity_id || '|' || strftime(period, '%Y-%m') || '|' || standard_category as pnl_key,
    entity_id,
    period,
    standard_category,
    pnl_group,
    is_intercompany,
    any_value(local_currency)  as local_currency,
    round(sum(amount_local), 2) as amount_local,
    round(sum(amount_usd), 2)   as amount_usd,
    round(sum(signed_usd), 2)   as net_income_impact_usd
from {{ ref('int_gl_usd') }}
group by entity_id, period, standard_category, pnl_group, is_intercompany
