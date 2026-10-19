-- Monthly average rates to USD. USD itself is always 1.0.
-- P&L lines use monthly average rates (standard practice for income statements).
select period, currency, usd_per_unit from {{ ref('fx_rates') }}
union all
select distinct period, 'USD' as currency, 1.0 as usd_per_unit from {{ ref('fx_rates') }}
