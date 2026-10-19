{{ config(severity='warn') }}
-- COA MAPPING (warning): low-confidence mappings a human should confirm.
select distinct entity_id, account_id, account_name, standard_category, mapping_confidence, mapping_method
from {{ ref('int_gl_usd') }}
where mapping_status = 'needs_review'
