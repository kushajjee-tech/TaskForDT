-- Convert every line to the reporting currency (USD) and add signs.
-- amount_*  : as reported (positive for both revenue and expenses)
-- signed_*  : contribution to net income (revenue +, expense -)
select
    g.entity_id,
    g.account_id,
    g.account_name,
    g.period,
    g.classification,
    g.is_intercompany,
    g.line_source,
    g.standard_category,
    s.pnl_group,
    s.category_sign,
    g.source_sign,
    g.mapping_method,
    g.mapping_status,
    g.mapping_confidence,
    e.functional_currency                          as local_currency,
    fx.usd_per_unit,
    g.amount_local,
    g.amount_local * g.source_sign                 as signed_local,
    round(g.amount_local * fx.usd_per_unit, 2)     as amount_usd,
    round(g.amount_local * fx.usd_per_unit, 2) * g.source_sign as signed_usd
from {{ ref('int_gl_mapped') }} g
join {{ ref('entities') }} e on e.entity_id = g.entity_id
left join {{ ref('int_fx_rates') }} fx
    on fx.period = g.period and fx.currency = e.functional_currency
left join {{ ref('standard_coa') }} s on s.standard_category = g.standard_category
