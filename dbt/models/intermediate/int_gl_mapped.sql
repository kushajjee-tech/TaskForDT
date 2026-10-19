-- Attach the standard chart-of-accounts category to every line.
select
    l.*,
    case l.account_id
        when 'IC-REV' then 'Intercompany Revenue'
        when 'IC-EXP' then 'Intercompany Expense'
        else m.standard_category
    end                                         as standard_category,
    case when l.is_intercompany then 'system' else m.method end   as mapping_method,
    case when l.is_intercompany then 'approved' else m.status end as mapping_status,
    case when l.is_intercompany then 1.0 else m.confidence end    as mapping_confidence
from {{ ref('int_gl_lines') }} l
left join {{ ref('coa_mapping') }} m
    on m.entity_id = l.entity_id and m.account_id = l.account_id
