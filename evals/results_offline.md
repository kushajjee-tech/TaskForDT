# COA mapper eval (rules + fallback)

| Metric | Value |
|---|---|
| Accounts in gold set | 60 |
| Overall accuracy | 47% (28/60) |
| Auto-approved (confidence >= 0.97) | 30% (18/60) |
| Accuracy of auto-approved | 100% (18/18) |
| Sent to human review | 42 |

| Stage | Accounts | Accuracy |
|---|---|---|
| fallback | 42 | 24% |
| rule | 18 | 100% |

## Threshold calibration (target: auto-approved accuracy >= 98%)

| Threshold | Auto-approved | Accuracy of auto-approved |
|---|---|---|
| 0.5 | 18/60 | 100.0% (18/18) |
| 0.6 | 18/60 | 100.0% (18/18) |
| 0.7 | 18/60 | 100.0% (18/18) |
| 0.8 | 18/60 | 100.0% (18/18) |
| 0.85 | 18/60 | 100.0% (18/18) |
| 0.9 | 18/60 | 100.0% (18/18) |
| 0.95 | 18/60 | 100.0% (18/18) |
| 0.97 | 18/60 | 100.0% (18/18) |
| 0.98 | 0/60 | - |
| 0.99 | 0/60 | - |
| 0.995 | 0/60 | - |
| 0.999 | 0/60 | - |

Recommended AUTO_APPROVE_CONFIDENCE: **0.97**

## Errors

| Account | Expected | Predicted | Conf. | Status |
|---|---|---|---|---|
| Services | Services Revenue | Product Revenue | 0.30 | needs_review |
| Consultancy Income | Services Revenue | Product Revenue | 0.30 | needs_review |
| Design income | Services Revenue | Product Revenue | 0.30 | needs_review |
| Landscaping Services | Services Revenue | Product Revenue | 0.30 | needs_review |
| Implementation Fees | Services Revenue | Product Revenue | 0.30 | needs_review |
| Employer's NI | Payroll & Benefits | Office & Admin | 0.30 | needs_review |
| Employee Pension Contributions | Payroll & Benefits | Office & Admin | 0.30 | needs_review |
| Health Insurance - Employees | Payroll & Benefits | Office & Admin | 0.30 | needs_review |
| Bonuses | Payroll & Benefits | Office & Admin | 0.30 | needs_review |
| Promotional | Marketing & Advertising | Office & Admin | 0.30 | needs_review |
| Trade Show Expenses | Marketing & Advertising | Office & Admin | 0.30 | needs_review |
| SaaS Tools | Software & Tools | Office & Admin | 0.30 | needs_review |
| Computer & Internet | Software & Tools | Office & Admin | 0.30 | needs_review |
| AWS | Software & Tools | Office & Admin | 0.30 | needs_review |
| Utilities | Rent & Facilities | Office & Admin | 0.30 | needs_review |
| Gas and Electric | Rent & Facilities | Office & Admin | 0.30 | needs_review |
| Building Repairs | Rent & Facilities | Office & Admin | 0.30 | needs_review |
| Business Rates | Rent & Facilities | Office & Admin | 0.30 | needs_review |
| Travel | Travel & Meals | Office & Admin | 0.30 | needs_review |
| Travel & Subsistence | Travel & Meals | Office & Admin | 0.30 | needs_review |
| Meals and Entertainment | Travel & Meals | Office & Admin | 0.30 | needs_review |
| Travel Meals | Travel & Meals | Office & Admin | 0.30 | needs_review |
| Accountancy Fees | Professional Fees | Office & Admin | 0.30 | needs_review |
| Bookkeeper | Professional Fees | Office & Admin | 0.30 | needs_review |
| Audit Fees | Professional Fees | Office & Admin | 0.30 | needs_review |
| Workers Compensation | Insurance | Office & Admin | 0.30 | needs_review |
| Card Processing Fees | Bank & Payment Fees | Office & Admin | 0.30 | needs_review |
| Stripe Fees | Bank & Payment Fees | Office & Admin | 0.30 | needs_review |
| Automobile | Vehicle & Equipment | Office & Admin | 0.30 | needs_review |
| Fuel | Vehicle & Equipment | Office & Admin | 0.30 | needs_review |
| Equipment Rental | Vehicle & Equipment | Office & Admin | 0.30 | needs_review |
| Corporation Tax | Income Tax | Office & Admin | 0.30 | needs_review |
