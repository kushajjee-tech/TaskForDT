# AI-ready interface: how agents should use this data

The rule: **agents call defined metrics; they never invent the math.**

| Agent needs | Use | Why |
|---|---|---|
| A number ("What was gross margin in Sep?") | `marts.mtr_monthly_metrics` | One definition per metric, same number as dashboards |
| A breakdown ("Which costs grew most?") | `marts.fct_pnl_consolidated_monthly` by `standard_category` | Standardized categories across entities |
| An entity view ("How is the UK doing?") | `marts.fct_pnl_entity_monthly` | Local currency and USD side by side |
| An explanation ("Why does consolidated revenue differ from the sum?") | `marts.fct_consolidation_bridge` | Shows eliminations explicitly |
| Trust signals ("Can I rely on this?") | health report, dbt test results, `mapping_status` | Agent should caveat answers when checks fail or mappings await review |

## Tool design (sketch)
- `get_metric(metric, period_range, entity=None)` → value(s) + definition + data freshness
- `get_breakdown(metric_group, period, by="standard_category")`
- `explain_variance(metric, period_a, period_b)` → top category drivers from the marts
- Every response includes **source tables, filters and freshness**, so answers are verifiable.

## Guardrails
- Read-only access; queries scoped to the customer's tenant and the user's permissions.
- If a reconciliation test is failing for the period asked about, the agent must say so.
- The LLM narrates; the warehouse calculates.
