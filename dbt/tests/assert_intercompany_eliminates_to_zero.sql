-- CONSOLIDATION: intercompany revenue and expense must cancel out each month in USD.
select period,
       round(sum(case when standard_category = 'Intercompany Revenue' then amount_usd else 0 end), 2) as ic_revenue,
       round(sum(case when standard_category = 'Intercompany Expense' then amount_usd else 0 end), 2) as ic_expense
from {{ ref('int_gl_usd') }}
where is_intercompany
group by period
having abs(sum(signed_usd)) > 0.01
