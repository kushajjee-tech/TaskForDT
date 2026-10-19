-- Chart-of-accounts mapping for the current source mode.
-- Sample and live data keep separate mapping seeds, because account ids are only unique
-- within one QuickBooks company: sample account 80 and sandbox account 80 are different
-- accounts. SOURCE_MODE (from .env) picks the seed: coa_mapping_sample or coa_mapping_live.
{% set mode = env_var('SOURCE_MODE', 'sample') %}
{% if mode not in ['sample', 'live'] %}
    {{ exceptions.raise_compiler_error("SOURCE_MODE must be 'sample' or 'live', got '" ~ mode ~ "'") }}
{% endif %}
select * from {{ ref('coa_mapping_' ~ mode) }}
