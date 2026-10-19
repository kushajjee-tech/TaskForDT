"""Extract QuickBooks data for each entity and load it into the warehouse.

Two sync patterns, because the two kinds of QuickBooks endpoints behave differently:
1. Accounts (entity API): true incremental sync on Metadata.LastUpdatedTime,
   with a saved cursor. Inactive accounts are included (soft deletes).
2. Monthly P&L (report API): reports have no "changed since" filter, and
   accountants back-date edits into open periods. So the first run backfills full
   history, and later runs re-pull a trailing lookback window and replace it.

Usage:
    python -m extract.extract                 # mode from SOURCE_MODE in .env
    python -m extract.extract --mode sample --simulate-edit recent
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from extract import load
from extract.qbo_client import QBOClient, SampleClient, TokenStore
from extract.qbo_parse import flatten_account, parse_pnl_report

STATE_PATH = Path("state/state.json")


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def _ts(value: str) -> datetime:
    """Compare QuickBooks timestamps as real datetimes (offsets differ across DST)."""
    return datetime.fromisoformat(value)


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))


def build_clients(mode: str, simulate_edit: str | None):
    if mode == "sample":
        return {e: SampleClient(e, simulate_edit=simulate_edit) for e in ("us", "uk")}
    store = TokenStore()
    clients = {}
    for e in ("us", "uk"):
        realm = os.environ.get(f"QBO_{e.upper()}_REALM_ID")
        if not realm:
            print(f"  skipping '{e}': QBO_{e.upper()}_REALM_ID not set")
            continue
        clients[e] = QBOClient(
            entity_id=e, realm_id=realm,
            client_id=os.environ["QBO_CLIENT_ID"], client_secret=os.environ["QBO_CLIENT_SECRET"],
            initial_refresh_token=os.environ.get(f"QBO_{e.upper()}_REFRESH_TOKEN", ""),
            environment=os.environ.get("QBO_ENVIRONMENT", "sandbox"), token_store=store)
    return clients


def sync_accounts(con, client, entity, st, run_id, mode):
    started = load.now()
    cursor = st.get("accounts_cursor")
    try:
        total, max_seen = 0, cursor
        for page in client.query_accounts(cursor):
            rows = [flatten_account(a) for a in page]
            total += load.upsert_accounts(con, entity, rows)
            for r in rows:
                if r["last_updated_at"] and (not max_seen or _ts(r["last_updated_at"]) > _ts(max_seen)):
                    max_seen = r["last_updated_at"]
        # Never move the cursor past the time this run started. Sandbox (and sometimes real)
        # companies have LastUpdatedTime values in the future; a cursor there would skip
        # genuine edits until that date. Re-pulling a few future-dated rows is harmless (upsert).
        run_start = started.replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
        if max_seen and _ts(max_seen) > _ts(run_start):
            max_seen = run_start
        st["accounts_cursor"] = max_seen
        load.log_run(con, run_id=run_id, entity_id=entity, stream="accounts", mode=mode,
                     started_at=started, status="success", rows_loaded=total)
        print(f"  [{entity}] accounts: {total} changed (cursor -> {max_seen})")
        return True
    except Exception as exc:  # noqa: BLE001
        load.log_run(con, run_id=run_id, entity_id=entity, stream="accounts", mode=mode,
                     started_at=started, status="failed", error=str(exc)[:500])
        print(f"  [{entity}] accounts FAILED: {exc}")
        return False


def sync_pnl(con, client, entity, st, run_id, mode, today, backfill_start, lookback):
    started = load.now()
    if st.get("pnl_backfilled"):
        window_start = max(add_months(month_start(today), -(lookback - 1)), backfill_start)
        kind = f"incremental (last {lookback} months)"
    else:
        window_start, kind = backfill_start, "historical backfill"
    try:
        parsed = parse_pnl_report(client.pnl_report(window_start, today, by_month=True))
        n = load.replace_pnl_window(con, entity, window_start, today,
                                    parsed["lines"], parsed["net_income"])
        totals = parse_pnl_report(client.pnl_report(backfill_start, today, by_month=False))["totals"]
        load.replace_period_totals(con, entity, backfill_start, today, totals)
        st["pnl_backfilled"] = True
        load.log_run(con, run_id=run_id, entity_id=entity, stream="pnl_monthly", mode=mode,
                     started_at=started, status="success", rows_loaded=n,
                     window_start=window_start, window_end=today)
        print(f"  [{entity}] P&L: {kind} {window_start} -> {today}, {n} account-month rows")
        return True
    except Exception as exc:  # noqa: BLE001
        load.log_run(con, run_id=run_id, entity_id=entity, stream="pnl_monthly", mode=mode,
                     started_at=started, status="failed", window_start=window_start,
                     window_end=today, error=str(exc)[:500])
        print(f"  [{entity}] P&L FAILED: {exc}")
        return False


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default=os.environ.get("SOURCE_MODE", "sample"), choices=["sample", "live"])
    ap.add_argument("--simulate-edit", choices=["recent", "old"], default=None,
                    help="sample mode only: simulate a back-dated edit in the books")
    args = ap.parse_args()

    today = date.today()
    backfill_start = date.fromisoformat(os.environ.get("BACKFILL_START", "2025-01-01"))
    lookback = int(os.environ.get("LOOKBACK_MONTHS", "3"))
    run_id = uuid.uuid4().hex[:12]

    print(f"Sync run {run_id} | mode={args.mode} | as of {today}")
    con, state, ok = load.connect(), load_state(), True
    for entity, client in build_clients(args.mode, args.simulate_edit).items():
        st = state.setdefault(entity, {})
        ok &= sync_accounts(con, client, entity, st, run_id, args.mode)
        ok &= sync_pnl(con, client, entity, st, run_id, args.mode, today, backfill_start, lookback)
        save_state(state)  # checkpoint after each entity
    con.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
