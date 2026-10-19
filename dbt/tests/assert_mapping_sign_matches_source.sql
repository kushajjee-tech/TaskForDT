-- AI GUARDRAIL: a mapping must not flip an account's direction, e.g. an AI mistake
-- that maps an expense account to a revenue category.
select distinct entity_id, account_id, account_name, classification, standard_category, mapping_method
from {{ ref('int_gl_usd') }}
where category_sign is not null and source_sign is not null and category_sign <> source_sign
