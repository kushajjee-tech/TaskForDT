"""QuickBooks Online API client (live) and a sample-data client with the same interface.

Both clients return raw QuickBooks-shaped JSON, so the same parsing and
loading code runs in both modes.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
API_HOSTS = {
    "sandbox": "https://sandbox-quickbooks.api.intuit.com",
    "production": "https://quickbooks.api.intuit.com",
}
MINOR_VERSION = "75"
RETRYABLE = {429, 500, 502, 503, 504}


class TokenStore:
    """Keeps the latest refresh token per entity. Intuit rotates refresh tokens,
    and only the newest one stays valid, so we must persist every new one."""

    def __init__(self, path: str = "state/tokens.json"):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def get(self, entity: str) -> dict:
        return self.data.get(entity, {})

    def save(self, entity: str, **values):
        self.data.setdefault(entity, {}).update(values)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))


class QBOClient:
    def __init__(self, entity_id, realm_id, client_id, client_secret,
                 initial_refresh_token, environment="sandbox", token_store=None):
        self.entity_id = entity_id
        self.realm_id = realm_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.base = f"{API_HOSTS[environment]}/v3/company/{realm_id}"
        self.tokens = token_store or TokenStore()
        if not self.tokens.get(entity_id).get("refresh_token"):
            self.tokens.save(entity_id, refresh_token=initial_refresh_token)
        self._access_token = None
        self._expires_at = 0.0

    # ---- auth -----------------------------------------------------------
    def _refresh(self):
        refresh_token = self.tokens.get(self.entity_id)["refresh_token"]
        resp = requests.post(
            TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"[{self.entity_id}] token refresh failed ({resp.status_code}): {resp.text[:300]}. "
                "Get a fresh refresh token from the OAuth 2.0 Playground.")
        body = resp.json()
        self._access_token = body["access_token"]
        self._expires_at = time.time() + int(body.get("expires_in", 3600)) - 60
        self.tokens.save(self.entity_id, refresh_token=body["refresh_token"],
                         rotated_at=datetime.utcnow().isoformat() + "Z")

    def _token(self):
        if not self._access_token or time.time() >= self._expires_at:
            self._refresh()
        return self._access_token

    # ---- http with retries ------------------------------------------------
    def _get(self, path: str, params: dict) -> dict:
        params = {**params, "minorversion": MINOR_VERSION}
        refreshed = False
        for attempt in range(6):
            resp = requests.get(
                f"{self.base}/{path}", params=params, timeout=60,
                headers={"Authorization": f"Bearer {self._token()}",
                         "Accept": "application/json"})
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 401 and not refreshed:
                self._refresh()
                refreshed = True
                continue
            if resp.status_code in RETRYABLE:
                wait = int(resp.headers.get("Retry-After", 0)) or min(2 ** attempt, 30)
                time.sleep(wait)
                continue
            raise RuntimeError(f"[{self.entity_id}] GET {path} failed "
                               f"({resp.status_code}): {resp.text[:300]}")
        raise RuntimeError(f"[{self.entity_id}] GET {path} failed after retries")

    # ---- endpoints -----------------------------------------------------------
    def query_accounts(self, since_iso: str | None, page_size: int = 1000):
        """Yield pages of Account objects changed since the cursor.
        Includes inactive accounts: QuickBooks 'deletes' accounts by marking them
        inactive (a soft delete), so we need them to keep the warehouse correct."""
        start = 1
        while True:
            where = "WHERE Active IN (true, false)"
            if since_iso:
                where += f" AND Metadata.LastUpdatedTime > '{since_iso}'"
            query = f"SELECT * FROM Account {where} STARTPOSITION {start} MAXRESULTS {page_size}"
            page = self._get("query", {"query": query}).get("QueryResponse", {}).get("Account", [])
            yield page
            if len(page) < page_size:
                break
            start += page_size

    def pnl_report(self, start: date, end: date, by_month: bool) -> dict:
        params = {"start_date": start.isoformat(), "end_date": end.isoformat(),
                  "accounting_method": "Accrual"}
        if by_month:
            params["summarize_column_by"] = "Month"
        return self._get("reports/ProfitAndLoss", params)


# =============================================================================
# Sample client: builds QuickBooks-shaped responses from bundled sample data
# =============================================================================
SECTION_BY_TYPE = {
    "Income": "Income", "Cost of Goods Sold": "COGS", "Expense": "Expenses",
    "Other Income": "OtherIncome", "Other Expense": "OtherExpenses",
}
SECTION_ORDER = ["Income", "COGS", "Expenses", "OtherIncome", "OtherExpenses"]
SECTION_SIGN = {"Income": 1, "COGS": -1, "Expenses": -1, "OtherIncome": 1, "OtherExpenses": -1}


def _months(start: date, end: date):
    cur = date(start.year, start.month, 1)
    while cur <= end:
        yield cur
        cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)


def _month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


class SampleClient:
    """Same interface as QBOClient, backed by sample_data/<entity>/.

    simulate_edit: 'recent' changes a figure inside the lookback window,
    'old' changes a figure outside it (the reconciliation test should catch that).
    """

    def __init__(self, entity_id: str, data_dir: str = "sample_data", simulate_edit: str | None = None):
        self.entity_id = entity_id
        root = Path(data_dir) / entity_id
        self.accounts = json.loads((root / "accounts.json").read_text())
        self.amounts = json.loads((root / "monthly_amounts.json").read_text())
        self.parents = {a["Id"]: a for a in self.accounts if a.get("_is_parent")}
        if simulate_edit:
            self._apply_edit(simulate_edit)

    def _apply_edit(self, kind: str):
        months = sorted({m for v in self.amounts.values() for m in v})
        target_month = months[-2] if kind == "recent" else months[2]
        acc_id = next(a["Id"] for a in self.accounts
                      if a["AccountType"] == "Expense" and not a.get("_is_parent"))
        self.amounts[acc_id][target_month] = round(
            self.amounts[acc_id].get(target_month, 0) + 1234.56, 2)
        print(f"  [sample:{self.entity_id}] simulated back-dated edit: account {acc_id}, "
              f"{target_month} +1234.56 ({kind})")

    def query_accounts(self, since_iso, page_size=1000):
        rows = [{k: v for k, v in a.items() if not k.startswith("_")} for a in self.accounts]
        if since_iso:
            rows = [a for a in rows if a["MetaData"]["LastUpdatedTime"] > since_iso]
        for i in range(0, max(len(rows), 1), page_size):
            yield rows[i:i + page_size]

    def pnl_report(self, start: date, end: date, by_month: bool) -> dict:
        months = list(_months(start, end))
        if by_month:
            cols = [{"ColTitle": m.strftime("%b %Y"), "ColType": "Money",
                     "MetaData": [{"Name": "StartDate", "Value": max(m, start).isoformat()},
                                  {"Name": "EndDate", "Value": min(_month_end(m), end).isoformat()},
                                  {"Name": "ColKey", "Value": m.strftime("%b %Y")}]} for m in months]
        else:
            cols = []
        cols.append({"ColTitle": "Total", "ColType": "Money",
                     "MetaData": [{"Name": "ColKey", "Value": "total"}]})
        columns = {"Column": [{"ColTitle": "", "ColType": "Account"}] + cols}

        def values_for(acc_id):
            series = self.amounts.get(acc_id, {})
            vals = [round(series.get(m.strftime("%Y-%m"), 0.0), 2) for m in months]
            return vals, round(sum(vals), 2)

        def fmt(v):
            return "" if v == 0 else f"{v:.2f}"

        sections, ni_by_month, ni_total = [], [0.0] * len(months), 0.0
        for sec in SECTION_ORDER:
            accs = [a for a in self.accounts if SECTION_BY_TYPE.get(a["AccountType"]) == sec]
            rows, sec_vals, sec_total = [], [0.0] * len(months), 0.0
            for a in accs:
                if a.get("_is_parent") or a.get("ParentRef"):
                    continue
                vals, tot = values_for(a["Id"])
                rows.append(self._data_row(a, vals, tot, by_month, fmt))
                sec_vals = [x + y for x, y in zip(sec_vals, vals)]
                sec_total += tot
            for p in [a for a in accs if a.get("_is_parent")]:  # nested sub-accounts
                children = [a for a in accs if (a.get("ParentRef") or {}).get("value") == p["Id"]]
                child_rows, p_vals, p_tot = [], [0.0] * len(months), 0.0
                for c in children:
                    vals, tot = values_for(c["Id"])
                    child_rows.append(self._data_row(c, vals, tot, by_month, fmt))
                    p_vals = [x + y for x, y in zip(p_vals, vals)]
                    p_tot += tot
                rows.append({
                    "Header": {"ColData": [{"value": p["Name"], "id": p["Id"]}] +
                               [{"value": ""} for _ in cols]},
                    "Rows": {"Row": child_rows},
                    "Summary": {"ColData": [{"value": f"Total {p['Name']}"}] +
                                ([{"value": fmt(v)} for v in p_vals] if by_month else []) +
                                [{"value": fmt(p_tot)}]},
                    "type": "Section"})
                sec_vals = [x + y for x, y in zip(sec_vals, p_vals)]
                sec_total += p_tot
            sections.append({"Header": {"ColData": [{"value": sec}]}, "Rows": {"Row": rows},
                             "Summary": {"ColData": [{"value": f"Total {sec}"}] +
                                         ([{"value": fmt(v)} for v in sec_vals] if by_month else []) +
                                         [{"value": fmt(sec_total)}]},
                             "type": "Section", "group": sec})
            ni_by_month = [n + SECTION_SIGN[sec] * v for n, v in zip(ni_by_month, sec_vals)]
            ni_total += SECTION_SIGN[sec] * sec_total
        sections.append({"Summary": {"ColData": [{"value": "Net Income"}] +
                                     ([{"value": fmt(round(v, 2))} for v in ni_by_month] if by_month else []) +
                                     [{"value": fmt(round(ni_total, 2))}]},
                         "type": "Section", "group": "NetIncome"})
        return {"Header": {"ReportName": "ProfitAndLoss", "StartPeriod": start.isoformat(),
                           "EndPeriod": end.isoformat()},
                "Columns": columns, "Rows": {"Row": sections}}

    @staticmethod
    def _data_row(acc, vals, tot, by_month, fmt):
        return {"ColData": [{"value": acc["Name"], "id": acc["Id"]}] +
                ([{"value": fmt(v)} for v in vals] if by_month else []) +
                [{"value": fmt(tot)}], "type": "Data"}
