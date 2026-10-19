-- Group-level P&L in USD: both entities combined, intercompany eliminated.
select
    strftime(period, '%Y-%m') || '|' || standard_category as pnl_key,
    period,
    standard_category,
    pnl_group,
    round(sum(amount_usd), 2) as amount_usd,
    round(sum(signed_usd), 2) as net_income_impact_usd
from {{ ref('int_gl_usd') }}
where not is_intercompany          -- the elimination step
group by period, standard_category, pnl_group
