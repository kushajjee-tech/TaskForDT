# COA mapper eval (rules + gpt-4o-mini) - BEFORE

One batched call, confidence self-reported by the model, threshold 0.8, original insurance rule.
The wrong mappings were reported at 0.97-1.00 confidence, so no threshold could separate them.

| Metric | Value |
|---|---|
| Accounts in gold set | 60 |
| Overall accuracy | 95% (57/60) |
| Auto-approved (confidence >= 0.8) | 100% (60/60) |
| Accuracy of auto-approved | 95% (57/60) |
| Sent to human review | 0 |

| Stage | Accounts | Accuracy |
|---|---|---|
| llm | 41 | 95% |
| rule | 19 | 95% |

## Errors

| Account | Expected | Predicted | Conf. | Status |
|---|---|---|---|---|
| Design income | Services Revenue | Product Revenue | 1.00 | approved |
| Health Insurance - Employees | Payroll & Benefits | Insurance | 0.97 | approved |
| Workers Compensation | Insurance | Payroll & Benefits | 1.00 | approved |
