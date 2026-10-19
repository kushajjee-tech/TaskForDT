"""Parse QuickBooks Online report JSON into flat rows.

QuickBooks reports are nested trees: sections (Income, Expenses, ...) contain
account rows, and parent accounts contain sub-account sections. We walk the
tree recursively and keep account rows (cells with an account id). Section
Summary rows are subtotals and are skipped, so nothing is double counted.

Parent accounts that also have postings of their own (seen in the live API):
the section Header row carries the parent's id and its direct amounts, while
the children are rows inside the section. So a Header with an id is read as an
account row too; its values exclude the children.
"""
from __future__ import annotations

import re
from datetime import date

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _num(value) -> float:
    if value in (None, ""):
        return 0.0
    return float(str(value).replace(",", ""))


def _meta(col: dict) -> dict:
    return {m.get("Name"): m.get("Value") for m in col.get("MetaData", []) or []}


def _column_period(col: dict) -> date | None:
    """Month a report column represents (first day of month)."""
    md = _meta(col)
    if md.get("StartDate"):
        d = date.fromisoformat(md["StartDate"])
        return date(d.year, d.month, 1)
    m = re.match(r"([A-Za-z]{3})\w*\s+(\d{4})", col.get("ColTitle", ""))
    if m and m.group(1)[:3].title() in _MONTHS:
        return date(int(m.group(2)), _MONTHS[m.group(1)[:3].title()], 1)
    return None


def parse_pnl_report(report: dict) -> dict:
    """Return {'lines': [...], 'net_income': {period: amount}, 'totals': [...]}.

    lines      -> one row per (account, month) with a non-zero amount
    net_income -> QuickBooks' own Net Income per month (used for reconciliation)
    totals     -> one row per account from a 'Total' column (used for reconciliation)
    """
    columns = report.get("Columns", {}).get("Column", [])
    col_info = []  # (index, period or None, is_total)
    for idx, col in enumerate(columns[1:], start=1):
        key = (_meta(col).get("ColKey") or col.get("ColTitle", "")).strip().lower()
        is_total = key == "total" or col.get("ColTitle", "").strip().lower() == "total"
        col_info.append((idx, None if is_total else _column_period(col), is_total))

    lines, totals, net_income = [], [], {}

    def read_account_row(cells, grp):
        account = cells[0]
        if not account.get("id"):
            return
        for idx, period, is_total in col_info:
            if idx >= len(cells):
                continue
            amount = _num(cells[idx].get("value"))
            if amount == 0:
                continue
            rec = {"account_id": str(account["id"]),
                   "account_name": account.get("value", ""),
                   "report_section": grp}
            if is_total:
                totals.append({**rec, "total_amount": amount})
            elif period:
                lines.append({**rec, "period": period, "amount": amount})

    def walk(rows, group):
        for row in rows or []:
            grp = row.get("group", group)
            if "ColData" in row:  # a data row
                read_account_row(row["ColData"], grp)
            else:  # a section: parent account's own postings, children, Net Income summary
                if row.get("Header"):
                    read_account_row(row["Header"].get("ColData") or [{}], grp)
                walk(row.get("Rows", {}).get("Row"), grp)
                if grp == "NetIncome" and row.get("Summary"):
                    cells = row["Summary"]["ColData"]
                    for idx, period, is_total in col_info:
                        if period and idx < len(cells):
                            net_income[period] = _num(cells[idx].get("value"))

    walk(report.get("Rows", {}).get("Row"), None)
    return {"lines": lines, "net_income": net_income, "totals": totals}


def flatten_account(acc: dict) -> dict:
    """QuickBooks Account entity -> flat row."""
    return {
        "account_id": str(acc["Id"]),
        "name": acc.get("Name"),
        "fully_qualified_name": acc.get("FullyQualifiedName", acc.get("Name")),
        "account_type": acc.get("AccountType"),
        "account_sub_type": acc.get("AccountSubType"),
        "classification": acc.get("Classification"),
        "currency": (acc.get("CurrencyRef") or {}).get("value"),
        "active": bool(acc.get("Active", True)),
        "last_updated_at": (acc.get("MetaData") or {}).get("LastUpdatedTime"),
    }
