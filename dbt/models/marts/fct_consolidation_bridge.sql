-- Shows how entity totals become the consolidated total:
--   sum of entities - intercompany eliminations = consolidated
with lines as (select * from {{ ref('int_gl_usd') }})
select
    period,
    round(sum(case when pnl_group = 'Revenue' then amount_usd else 0 end), 2)                         as revenue_all_entities,
    round(sum(case when pnl_group = 'Revenue' and is_intercompany then amount_usd else 0 end), 2)     as revenue_eliminated,
    round(sum(case when pnl_group = 'Revenue' and not is_intercompany then amount_usd else 0 end), 2) as revenue_consolidated,
    round(sum(case when pnl_group = 'OpEx' then amount_usd else 0 end), 2)                            as opex_all_entities,
    round(sum(case when pnl_group = 'OpEx' and is_intercompany then amount_usd else 0 end), 2)        as opex_eliminated,
    round(sum(case when pnl_group = 'OpEx' and not is_intercompany then amount_usd else 0 end), 2)    as opex_consolidated,
    round(sum(signed_usd), 2)                                                                         as net_income_all_entities,
    round(sum(case when not is_intercompany then signed_usd else 0 end), 2)                           as net_income_consolidated
from lines
group by period
order by period
