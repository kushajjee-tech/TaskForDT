"""Stage 1: deterministic rules. Cheap, instant and predictable.
Only high-precision rules live here; everything else goes to the LLM."""
from __future__ import annotations

import re

# Words that mark an account as an employee benefit (health cover, pension, etc.).
# Those costs belong to Payroll & Benefits, even when the name says "insurance".
EMPLOYEE_BENEFIT = r"\b(employees?|staff|health|medical|dental|vision|pensions?|benefits?|401\(?k\)?)"

# (pattern on account name, allowed QuickBooks account types, category, exclude pattern or None)
# Rules are checked in order and the first match wins.
RULES = [
    (r"\b(cost of goods sold|cost of sales|cogs)\b", {"Cost of Goods Sold"}, "Cost of Revenue", None),
    (r"\b(salar|wages|payroll)", {"Expense"}, "Payroll & Benefits", None),
    (r"\b(advertis|marketing)", {"Expense"}, "Marketing & Advertising", None),
    (r"\b(software|subscriptions?)\b", {"Expense"}, "Software & Tools", None),
    (r"\b(rent|lease)\b", {"Expense"}, "Rent & Facilities", None),
    (r"\b(legal|professional fees)\b", {"Expense"}, "Professional Fees", None),
    # Business insurance only: "Health Insurance - Employees" or "Staff Life Insurance" is a
    # benefit, so it is excluded here and left to the LLM (which sees the full taxonomy).
    (r"\binsurance\b", {"Expense"}, "Insurance", EMPLOYEE_BENEFIT),
    (r"\bbank charges\b", {"Expense"}, "Bank & Payment Fees", None),
    (r"\b(depreciation|amortization|amortisation)\b", {"Expense", "Other Expense"}, "Depreciation & Amortization", None),
    (r"\binterest (earned|income)\b", {"Other Income", "Income"}, "Other Income", None),
]

# Used only when no LLM is available (offline mode): a weak guess by account type,
# always sent to human review.
TYPE_FALLBACK = {
    "Income": "Product Revenue",
    "Cost of Goods Sold": "Cost of Revenue",
    "Expense": "Office & Admin",
    "Other Income": "Other Income",
    "Other Expense": "Other Expense",
}


def apply_rules(name: str, account_type: str):
    text = (name or "").lower()
    for pattern, types, category, exclude in RULES:
        if exclude and re.search(exclude, text):
            continue
        if account_type in types and re.search(pattern, text):
            return category, 0.97, f"rule: '{pattern}' on {account_type} account"
    if account_type == "Cost of Goods Sold":
        return "Cost of Revenue", 0.95, "rule: QuickBooks account type is Cost of Goods Sold"
    return None


def fallback(account_type: str):
    category = TYPE_FALLBACK.get(account_type, "Office & Admin")
    return category, 0.3, f"fallback: default for {account_type} accounts (no LLM available)"
