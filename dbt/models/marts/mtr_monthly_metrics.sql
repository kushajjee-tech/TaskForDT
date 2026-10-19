-- Metrics layer: each metric is defined once here and reused everywhere
-- (dashboards, forecasts, AI agents). Consolidated, USD, intercompany eliminated.
with p as (select * from {{ ref('fct_pnl_consolidated_monthly') }})
select
    period,
    round(sum(case when pnl_group = 'Revenue' then amount_usd else 0 end), 2) as revenue,
    round(sum(case when pnl_group = 'COGS'    then amount_usd else 0 end), 2) as cost_of_revenue,
    round(sum(case when pnl_group = 'Revenue' then amount_usd else 0 end)
        - sum(case when pnl_group = 'COGS'    then amount_usd else 0 end), 2) as gross_profit,
    round(100.0 * (sum(case when pnl_group = 'Revenue' then amount_usd else 0 end)
        - sum(case when pnl_group = 'COGS' then amount_usd else 0 end))
        / nullif(sum(case when pnl_group = 'Revenue' then amount_usd else 0 end), 0), 1) as gross_margin_pct,
    round(sum(case when pnl_group = 'OpEx'    then amount_usd else 0 end), 2) as operating_expenses,
    round(sum(case when pnl_group in ('Revenue', 'COGS', 'OpEx') then net_income_impact_usd else 0 end), 2) as operating_income,
    round(sum(net_income_impact_usd), 2)                                       as net_income,
    -- Net burn (P&L proxy): monthly loss. A cash-based burn would use the cash flow statement.
    round(greatest(-sum(net_income_impact_usd), 0), 2)                         as net_burn
from p
group by period
order by period
