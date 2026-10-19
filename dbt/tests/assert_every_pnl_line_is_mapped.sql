-- COA MAPPING: every account with P&L activity must map to a standard category.
select entity_id, account_id, any_value(account_name) as account_name, count(*) as lines
from {{ ref('int_gl_usd') }}
where standard_category is null or pnl_group is null
group by 1, 2
