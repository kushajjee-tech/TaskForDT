"""Generate QuickBooks-shaped sample data for two entities: Acme Inc (US, USD)
and Acme Ltd (UK, GBP). Account names deliberately differ between the two
companies, which is the real-world chart-of-accounts mapping problem."""
import json
import random
from pathlib import Path

random.seed(7)
MONTHS = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13) if (y, m) <= (2026, 10)]

# (Id, Name, AccountType, AccountSubType, Classification, base monthly amount, growth/mo)
US = [
    ("79", "Sales of Product Income", "Income", "SalesOfProductIncome", "Revenue", 182000, 0.020),
    ("80", "Services", "Income", "ServiceFeeIncome", "Revenue", 64000, 0.015),
    ("81", "Cost of Goods Sold", "Cost of Goods Sold", "SuppliesMaterialsCogs", "Expense", 71000, 0.018),
    ("90", "Payroll Expenses", "Expense", "PayrollExpenses", "Expense", 0, 0),  # parent
    ("91", "Salaries & Wages", "Expense", "PayrollExpenses", "Expense", 88000, 0.010),
    ("92", "Payroll Taxes", "Expense", "PayrollExpenses", "Expense", 7400, 0.010),
    ("7", "Advertising", "Expense", "AdvertisingPromotional", "Expense", 14500, 0.012),
    ("58", "Software Subscriptions", "Expense", "OfficeGeneralAdministrativeExpenses", "Expense", 9200, 0.020),
    ("57", "Rent or Lease", "Expense", "RentOrLeaseOfBuildings", "Expense", 12000, 0.0),
    ("41", "Travel", "Expense", "Travel", "Expense", 4300, 0.005),
    ("12", "Legal & Professional Fees", "Expense", "LegalProfessionalFees", "Expense", 6100, 0.0),
    ("15", "Office Expenses", "Expense", "OfficeGeneralAdministrativeExpenses", "Expense", 1800, 0.0),
    ("62", "Insurance", "Expense", "Insurance", "Expense", 2100, 0.0),
    ("8", "Bank Charges", "Expense", "BankCharges", "Expense", 650, 0.0),
    ("63", "Depreciation", "Other Expense", "Depreciation", "Expense", 3200, 0.0),
    ("82", "Interest Earned", "Other Income", "InterestEarned", "Revenue", 900, 0.0),
]
UK = [
    ("101", "Turnover", "Income", "SalesOfProductIncome", "Revenue", 61000, 0.022),
    ("102", "Consultancy Income", "Income", "ServiceFeeIncome", "Revenue", 23000, 0.015),
    ("103", "Cost of Sales", "Cost of Goods Sold", "SuppliesMaterialsCogs", "Expense", 24500, 0.020),
    ("110", "Staff Salaries", "Expense", "PayrollExpenses", "Expense", 38000, 0.010),
    ("111", "Employer's NI", "Expense", "PayrollExpenses", "Expense", 4600, 0.010),
    ("112", "Marketing", "Expense", "AdvertisingPromotional", "Expense", 5200, 0.012),
    ("113", "SaaS Tools", "Expense", "OfficeGeneralAdministrativeExpenses", "Expense", 3100, 0.020),
    ("114", "Office Rent", "Expense", "RentOrLeaseOfBuildings", "Expense", 6500, 0.0),
    ("115", "Travel & Subsistence", "Expense", "Travel", "Expense", 1700, 0.005),
    ("116", "Accountancy Fees", "Expense", "LegalProfessionalFees", "Expense", 1900, 0.0),
    ("117", "Stationery", "Expense", "OfficeGeneralAdministrativeExpenses", "Expense", 350, 0.0),
    ("118", "Business Insurance", "Expense", "Insurance", "Expense", 800, 0.0),
    ("119", "Card Processing Fees", "Expense", "BankCharges", "Expense", 420, 0.0),
    ("120", "Depreciation", "Other Expense", "Depreciation", "Expense", 1100, 0.0),
    ("121", "Bank Interest Received", "Other Income", "InterestEarned", "Revenue", 240, 0.0),
]


def build(rows, currency, parent_children=None):
    parent_children = parent_children or {}
    child_to_parent = {c: p for p, cs in parent_children.items() for c in cs}
    accounts, amounts = [], {}
    for acc_id, name, atype, sub, cls, base, growth in rows:
        acc = {"Id": acc_id, "Name": name, "AccountType": atype, "AccountSubType": sub,
               "Classification": cls, "CurrencyRef": {"value": currency}, "Active": True,
               "FullyQualifiedName": name,
               "MetaData": {"LastUpdatedTime": f"2025-0{random.randint(1, 6)}-1{random.randint(0, 9)}T09:00:00-07:00"}}
        if acc_id in parent_children:
            acc["_is_parent"] = True
        if acc_id in child_to_parent:
            parent_name = next(r[1] for r in rows if r[0] == child_to_parent[acc_id])
            acc["ParentRef"] = {"value": child_to_parent[acc_id]}
            acc["SubAccount"] = True
            acc["FullyQualifiedName"] = f"{parent_name}:{name}"
        accounts.append(acc)
        if base:
            amounts[acc_id] = {m: round(base * (1 + growth) ** i * random.uniform(0.93, 1.07), 2)
                               for i, m in enumerate(MONTHS)}
    return accounts, amounts


for entity, rows, currency, parents in [("us", US, "USD", {"90": ["91", "92"]}), ("uk", UK, "GBP", {})]:
    accounts, amounts = build(rows, currency, parents)
    out = Path("sample_data") / entity
    out.mkdir(parents=True, exist_ok=True)
    (out / "accounts.json").write_text(json.dumps(accounts, indent=2))
    (out / "monthly_amounts.json").write_text(json.dumps(amounts, indent=2))
    print(f"{entity}: {len(accounts)} accounts, {len(MONTHS)} months")
