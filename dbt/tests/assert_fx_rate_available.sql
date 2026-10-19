-- CURRENCY: every line needs an exchange rate for its month and currency.
select entity_id, period, local_currency, count(*) as lines_without_rate
from {{ ref('int_gl_usd') }}
where usd_per_unit is null
group by 1, 2, 3
