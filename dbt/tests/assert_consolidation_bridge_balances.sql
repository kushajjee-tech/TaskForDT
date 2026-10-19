-- CONSOLIDATION: all entities - eliminations = consolidated, and net income is unchanged
-- by elimination (both sides of an intercompany charge cancel).
select *
from {{ ref('fct_consolidation_bridge') }}
where abs(revenue_all_entities - revenue_eliminated - revenue_consolidated) > 0.01
   or abs(opex_all_entities - opex_eliminated - opex_consolidated) > 0.01
   or abs(net_income_all_entities - net_income_consolidated) > 0.01
