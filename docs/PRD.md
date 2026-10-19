# PRD: Finance onboarding in a day

## Problem
New customers wait weeks before they see a trusted number. Most of that time goes to four manual steps: getting accounting data out, mapping each customer's chart of accounts to our standard, converting currencies and consolidating entities, and proving the result matches the books. Every step is repeated per customer, and errors surface in front of the CFO.

## Goal
Cut time from "connect accounting system" to "first trusted consolidated P&L" from weeks to under a day for QuickBooks customers with up to a few entities, without lowering accuracy.

## Users
- **Implementation team (internal):** runs onboarding, resolves mapping questions.
- **Customer FP&A / controller (external):** connects the source, confirms mappings, signs off numbers.
- **AI/ML team (internal):** consumes clean, defined metrics for AI features.

## Scope (v1)
1. QuickBooks Online connector: accounts (incremental) and monthly P&L (backfill + lookback), multi-company.
2. COA mapping: rules → LLM → guardrails → review queue; only new accounts processed.
3. Monthly average FX conversion to the reporting currency.
4. Consolidation with intercompany elimination; consolidation bridge.
5. Reconciliation and data quality tests on every run.
6. Metrics layer: revenue, cost of revenue, gross profit and margin, opex, operating income, net income, net burn (P&L proxy).
7. Platform health report.

**Out of scope:** balance sheet, cash flow, departments/classes, review UI, other ERPs.

## Success metrics
| Metric | Target |
|---|---|
| Time to first trusted P&L (connect → all reconciliation tests green) | < 1 day, incl. human mapping review |
| Mapping: share auto-approved | ≥ 70% with LLM |
| Mapping: accuracy of auto-approved | ≥ 95% on gold set |
| Reconciliation to source | 100% of accounts and months within $0.01 |
| Sync success rate | ≥ 99% of scheduled runs |
| Data freshness | ≤ 24h behind source |

## Acceptance criteria
1. Re-running any sync creates no duplicate rows (idempotent loads).
2. An edit inside the lookback window is picked up on the next sync; an edit outside it is **detected** by the reconciliation test.
3. For every entity, account and synced month, modeled amounts equal QuickBooks report totals within $0.01.
4. Modeled net income equals QuickBooks net income per entity and month within $0.01.
5. Intercompany revenue and expense net to zero in USD every month; consolidated = sum of entities − eliminations.
6. Every account with P&L activity maps to exactly one standard category; no mapping flips revenue/expense direction.
7. Mappings below the confidence threshold appear in a review queue and in the health report.
8. Every non-USD line has an FX rate for its month.
9. The health report shows sync success rate, freshness per stream, test results and accounts awaiting review.

## Risks and open questions
- **LLM confidence is self-reported:** mitigated by eval-based thresholds and the direction guardrail.
- **Report API limits on large companies:** may need date-window chunking for backfills.
- **Mid-month FX policy and intercompany FX differences:** need a finance-approved policy per customer.
- **Customer-specific metric definitions** (e.g. ARR, burn): defaults plus per-customer overrides.
