-- All P&L lines per entity and month: QuickBooks lines plus intercompany lines.
-- QuickBooks sandboxes don't contain intercompany activity, so a seed simulates a
-- monthly management fee booked in both entities (in production it comes from the ERP).
with qbo_lines as (
    select
        p.entity_id, p.account_id, p.account_name, p.period, p.amount_local,
        a.classification, a.source_sign,
        false as is_intercompany, 'quickbooks' as line_source
    from {{ ref('stg_qbo__pnl_monthly') }} p
    left join {{ ref('stg_qbo__accounts') }} a using (entity_id, account_id)
),

synced_periods as (
    select entity_id, period from qbo_lines group by 1, 2
),

ic as (
    select t.*
    from {{ ref('intercompany_transactions') }} t
    where exists (select 1 from synced_periods s where s.entity_id = t.provider_entity and s.period = t.period)
      and exists (select 1 from synced_periods s where s.entity_id = t.recipient_entity and s.period = t.period)
),

-- Each side books the fee in its own currency at the month's average rate,
-- so the two sides net to exactly zero in USD.
ic_lines as (
    select ic.provider_entity as entity_id, 'IC-REV' as account_id,
           'Intercompany Management Fee Income' as account_name, ic.period,
           ic.fee_usd / fx.usd_per_unit as amount_local,
           'Revenue' as classification, 1 as source_sign
    from ic
    join {{ ref('entities') }} e on e.entity_id = ic.provider_entity
    join {{ ref('int_fx_rates') }} fx on fx.period = ic.period and fx.currency = e.functional_currency
    union all
    select ic.recipient_entity, 'IC-EXP', 'Intercompany Management Fee Expense', ic.period,
           ic.fee_usd / fx.usd_per_unit, 'Expense', -1
    from ic
    join {{ ref('entities') }} e on e.entity_id = ic.recipient_entity
    join {{ ref('int_fx_rates') }} fx on fx.period = ic.period and fx.currency = e.functional_currency
)

select * from qbo_lines
union all
select entity_id, account_id, account_name, period, amount_local, classification, source_sign,
       true as is_intercompany, 'intercompany_seed' as line_source
from ic_lines
