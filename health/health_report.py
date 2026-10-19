"""Platform health report: is the data fresh, complete and trustworthy?

Combines sync logs, dbt test results, mapping status and onboarding timing into
reports/platform_health.md. These are the metrics the Data Platform PM owns:
sync reliability, data freshness, error rates, time to first insight.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import duckdb

DB = os.environ.get("WAREHOUSE_PATH", "warehouse/finance.duckdb")
RUN_RESULTS = Path("dbt/target/run_results.json")
TIMING = Path("state/onboarding_timing.json")
OUT = Path("reports/platform_health.md")

TEST_GROUPS = {
    "Reconciliation (ties to QuickBooks)": ["assert_pnl_ties_to_source_report", "assert_net_income_ties_to_source"],
    "Consolidation (intercompany, bridge)": ["assert_intercompany_eliminates_to_zero", "assert_consolidation_bridge_balances"],
    "COA mapping completeness and guardrails": ["assert_every_pnl_line_is_mapped", "assert_mapping_sign_matches_source"],
    "Currency (FX rates present)": ["assert_fx_rate_available"],
}


def main():
    con = duckdb.connect(DB, read_only=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    lines = [f"# Platform health report", f"_Generated {now:%Y-%m-%d %H:%M} UTC_", ""]

    # --- sync reliability & freshness ----------------------------------------
    runs = con.execute("""
        select entity_id, stream, count(*) total,
               count(*) filter (where status = 'success') ok,
               max(finished_at) filter (where status = 'success') last_success,
               arg_max(status, finished_at) last_status,
               arg_max(error, finished_at) last_error
        from raw.sync_runs group by 1, 2 order by 1, 2""").fetchall()
    total = sum(r[2] for r in runs)
    ok = sum(r[3] for r in runs)
    lines += ["## Sync reliability and freshness", "",
              f"**Sync success rate:** {ok}/{total} stream runs ({ok/max(total,1):.0%})", "",
              "| Entity | Stream | Success | Last status | Freshness |", "|---|---|---|---|---|"]
    for e, s, t, o, last, status, err in runs:
        age = f"{(now - last).total_seconds()/3600:.1f} h ago" if last else "never"
        flag = "" if status == "success" else f" ⚠️ {err[:60] if err else ''}"
        lines.append(f"| {e} | {s} | {o}/{t} | {status}{flag} | {age} |")

    # --- data quality (dbt) -----------------------------------------------------------
    lines += ["", "## Data quality checks (dbt)", ""]
    if RUN_RESULTS.exists():
        results = json.loads(RUN_RESULTS.read_text())["results"]
        tests = [r for r in results if r["unique_id"].startswith("test.")]
        counts = {}
        for r in tests:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        lines.append("**Tests:** " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        lines += ["", "| Check group | Result |", "|---|---|"]
        by_name = {r["unique_id"].split(".")[2]: r for r in tests}
        for group, names in TEST_GROUPS.items():
            st = [by_name[n]["status"] for n in names if n in by_name]
            res = "✅ pass" if st and all(x == "pass" for x in st) else ("not run" if not st else "❌ " + ", ".join(st))
            lines.append(f"| {group} | {res} |")
        failing = [r for r in tests if r["status"] in ("fail", "error")]
        for r in failing:
            lines.append(f"- ❌ `{r['unique_id'].split('.')[2]}`: {r.get('message') or r.get('failures')} rows")
    else:
        lines.append("_No dbt results yet: run `dbt build`._")

    # --- mapping ---------------------------------------------------------------------
    m = con.execute("""
        select count(distinct entity_id || account_id),
               count(distinct entity_id || account_id) filter (where mapping_status = 'needs_review'),
               count(distinct entity_id || account_id) filter (where mapping_method = 'llm'),
               count(distinct entity_id || account_id) filter (where mapping_method = 'rule')
        from intermediate.int_gl_usd where line_source = 'quickbooks'""").fetchone()
    lines += ["", "## Chart of accounts mapping", "",
              f"- Accounts with activity: **{m[0]}**  (rules: {m[3]}, AI: {m[2]})",
              f"- Waiting for human review: **{m[1]}**"]

    # --- onboarding --------------------------------------------------------------------
    lines += ["", "## Onboarding", ""]
    if TIMING.exists():
        t = json.loads(TIMING.read_text())
        lines.append(f"- **Time to first trusted P&L:** {t['total_seconds']:.0f} seconds "
                     f"(mode: {t['mode']}, {t['finished_at']})")
        for step, secs in t["steps"].items():
            lines.append(f"  - {step}: {secs:.1f}s")
        lines.append(f"- Human review still needed for {m[1]} account mappings before sign-off.")
    else:
        lines.append("_Run `./run_onboarding.sh` to measure time to first insight._")

    built = con.execute("""select count(*) from information_schema.tables
                           where table_schema = 'marts' and table_name = 'mtr_monthly_metrics'""").fetchone()[0]
    latest = built and con.execute("select max(period) from marts.mtr_monthly_metrics").fetchone()[0]
    if not built:
        lines += ["", "_Metrics not built: dbt stopped downstream of a failing check (see above)._"]
    elif latest:
        rev, ni = con.execute("select revenue, net_income from marts.mtr_monthly_metrics where period = ?",
                              [latest]).fetchone()
        lines += ["", f"_Latest month {latest:%b %Y}: consolidated revenue ${rev:,.0f}, net income ${ni:,.0f}._"]

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
