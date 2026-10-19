# COA mapper eval (rules + gpt-4o-mini) - AFTER

One call per account, confidence = probability of the category tokens (logprobs), insurance rule fix,
revenue review policy, threshold calibrated below.

| Metric | Value |
|---|---|
| Accounts in gold set | 60 |
| Overall accuracy | 100% (60/60) |
| Auto-approved (confidence >= 0.97) | 87% (52/60) |
| Accuracy of auto-approved | 100% (52/52) |
| Sent to human review | 8 |

| Stage | Accounts | Accuracy |
|---|---|---|
| llm | 42 | 100% |
| rule | 18 | 100% |

## Threshold calibration (target: auto-approved accuracy >= 98%)

| Threshold | Auto-approved | Accuracy of auto-approved |
|---|---|---|
| 0.5 | 52/60 | 100.0% (52/52) |
| 0.6 | 52/60 | 100.0% (52/52) |
| 0.7 | 52/60 | 100.0% (52/52) |
| 0.8 | 52/60 | 100.0% (52/52) |
| 0.85 | 52/60 | 100.0% (52/52) |
| 0.9 | 52/60 | 100.0% (52/52) |
| 0.95 | 52/60 | 100.0% (52/52) |
| 0.97 | 52/60 | 100.0% (52/52) |
| 0.98 | 34/60 | 100.0% (34/34) |
| 0.99 | 34/60 | 100.0% (34/34) |
| 0.995 | 34/60 | 100.0% (34/34) |
| 0.999 | 34/60 | 100.0% (34/34) |

Recommended AUTO_APPROVE_CONFIDENCE: **0.97**
