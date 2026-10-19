{{ config(severity='warn') }}
-- COA MAPPING (warning): mappings a human should confirm (below the confidence threshold,
-- or revenue, which always gets human review on first mapping).
select distinct entity_id, account_id, account_name, standard_category, mapping_confidence, mapping_method
from {{ ref('int_gl_usd') }}
where mapping_status = 'needs_review'
