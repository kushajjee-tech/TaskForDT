"""Load extracted rows into the DuckDB warehouse (raw schema).

Every load is idempotent: re-running a sync never creates duplicates.
- accounts: upsert on (entity_id, account_id)
- monthly P&L: replace the synced window for that entity (delete + insert)
- period totals: replace per entity (used only for reconciliation)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import duckdb

DB_PATH = os.environ.get("WAREHOUSE_PATH", "warehouse/finance.duckdb")

DDL = """
create schema if not exists raw;
create table if not exists raw.qbo_accounts (
    entity_id varchar, account_id varchar, name varchar, fully_qualified_name varchar,
    account_type varchar, account_sub_type varchar, classification varchar,
    currency varchar, active boolean, last_updated_at varchar, _loaded_at timestamp);
create table if not exists raw.qbo_pnl_monthly (
    entity_id varchar, account_id varchar, account_name varchar, report_section varchar,
    period date, amount double, _loaded_at timestamp);
create table if not exists raw.qbo_pnl_net_income (
    entity_id varchar, period date, net_income double, _loaded_at timestamp);
create table if not exists raw.qbo_pnl_period_totals (
    entity_id varchar, account_id varchar, account_name varchar, report_section varchar,
    range_start date, range_end date, total_amount double, _loaded_at timestamp);
create table if not exists raw.sync_runs (
    run_id varchar, entity_id varchar, stream varchar, mode varchar,
    started_at timestamp, finished_at timestamp, status varchar,
    rows_loaded integer, window_start date, window_end date, error varchar);
"""


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = duckdb.connect(DB_PATH)
    con.execute(DDL)
    return con


def upsert_accounts(con, entity_id, rows):
    if not rows:
        return 0
    ts = now()
    con.executemany("delete from raw.qbo_accounts where entity_id = ? and account_id = ?",
                    [(entity_id, r["account_id"]) for r in rows])
    con.executemany(
        "insert into raw.qbo_accounts values (?,?,?,?,?,?,?,?,?,?,?)",
        [(entity_id, r["account_id"], r["name"], r["fully_qualified_name"], r["account_type"],
          r["account_sub_type"], r["classification"], r["currency"], r["active"],
          r["last_updated_at"], ts) for r in rows])
    return len(rows)


def replace_pnl_window(con, entity_id, start, end, lines, net_income):
    ts = now()
    con.execute("begin")
    con.execute("delete from raw.qbo_pnl_monthly where entity_id = ? and period between ? and ?",
                [entity_id, start.replace(day=1), end])
    con.execute("delete from raw.qbo_pnl_net_income where entity_id = ? and period between ? and ?",
                [entity_id, start.replace(day=1), end])
    if lines:
        con.executemany("insert into raw.qbo_pnl_monthly values (?,?,?,?,?,?,?)",
                        [(entity_id, l["account_id"], l["account_name"], l["report_section"],
                          l["period"], l["amount"], ts) for l in lines])
    if net_income:
        con.executemany("insert into raw.qbo_pnl_net_income values (?,?,?,?)",
                        [(entity_id, p, v, ts) for p, v in net_income.items()])
    con.execute("commit")
    return len(lines)


def replace_period_totals(con, entity_id, start, end, totals):
    ts = now()
    con.execute("delete from raw.qbo_pnl_period_totals where entity_id = ?", [entity_id])
    if totals:
        con.executemany("insert into raw.qbo_pnl_period_totals values (?,?,?,?,?,?,?,?)",
                        [(entity_id, t["account_id"], t["account_name"], t["report_section"],
                          start, end, t["total_amount"], ts) for t in totals])
    return len(totals)


def log_run(con, **r):
    con.execute("insert into raw.sync_runs values (?,?,?,?,?,?,?,?,?,?,?)",
                [r["run_id"], r["entity_id"], r["stream"], r["mode"], r["started_at"], now(),
                 r["status"], r.get("rows_loaded", 0), r.get("window_start"),
                 r.get("window_end"), r.get("error")])
