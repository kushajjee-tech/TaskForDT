"""Onboarding results report: one self-contained HTML page for a busy founder.

Reads the real warehouse (DuckDB), dbt test results, onboarding timing and the AI eval
results, and writes reports/onboarding_report.html. No external CSS, JS or fonts: the
file can be emailed or opened offline.

Sections (top to bottom, most important first):
  1. Verdict + headline numbers      4. Consolidation bridge (US + UK - eliminations = group)
  2. Data flow, with live counts     5. Chart of accounts mapping (review queue first)
  3. Health scorecard                6. AI mapper eval, before vs after
  and the latest consolidated P&L.

Usage:
    python -m health.onboarding_report      (run_onboarding.sh runs it as the last step)
"""
from __future__ import annotations

import html
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

from health.health_report import RUN_RESULTS, TEST_GROUPS, TIMING

DB = os.environ.get("WAREHOUSE_PATH", "warehouse/finance.duckdb")
OUT = Path("reports/onboarding_report.html")
EVAL_BEFORE = Path("evals/results_llm_before.md")
EVAL_AFTER = Path("evals/results_llm_after.md")


# ---- formatting helpers -------------------------------------------------------------
def esc(value) -> str:
    return html.escape(str(value))


def money(value, parens: bool = True) -> str:
    """$1,234 / ($1,234) for negatives, the way finance teams read P&Ls."""
    if value is None:
        return "–"
    value = round(value)
    if value < 0 and parens:
        return f"(${-value:,.0f})"
    return f"${value:,.0f}"


def month_label(d: date) -> str:
    today = date.today()
    mtd = " (MTD)" if (d.year, d.month) == (today.year, today.month) else ""
    return f"{d:%b %Y}{mtd}"


def table(headers: list[str], rows: list[list[str]], numeric_from: int = 1, row_classes=None) -> str:
    """HTML table; columns from `numeric_from` on are right-aligned. Cells are pre-escaped HTML."""
    head = "".join(f'<th class="{"num" if i >= numeric_from else ""}">{esc(h)}</th>'
                   for i, h in enumerate(headers))
    body = ""
    for r_i, row in enumerate(rows):
        cls = (row_classes or [""] * len(rows))[r_i]
        body += f'<tr class="{cls}">' + "".join(
            f'<td class="{"num" if i >= numeric_from else ""}">{c}</td>' for i, c in enumerate(row)) + "</tr>"
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def pill(ok: bool | None, text: str) -> str:
    kind = "ok" if ok else ("warn" if ok is None else "bad")
    return f'<span class="pill {kind}">{esc(text)}</span>'


# ---- data -----------------------------------------------------------------------------
def load_tests() -> dict:
    """dbt test results: overall counts + one status per check group."""
    if not RUN_RESULTS.exists():
        return {"counts": {}, "groups": {}, "failing": []}
    results = json.loads(RUN_RESULTS.read_text())["results"]
    tests = {r["unique_id"].split(".")[2]: r["status"] for r in results if r["unique_id"].startswith("test.")}
    counts = {}
    for status in tests.values():
        counts[status] = counts.get(status, 0) + 1
    groups = {g: [tests[n] for n in names if n in tests] for g, names in TEST_GROUPS.items()}
    return {"counts": counts, "groups": groups,
            "failing": [n for n, s in tests.items() if s in ("fail", "error")]}


def parse_eval(path: Path) -> dict:
    """Read the headline metrics table of an eval results file: {'Overall accuracy': '95% (57/60)', ...}."""
    if not path.exists():
        return {}
    metrics = {}
    for line in path.read_text().splitlines():
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", line)
        if m and m.group(1) not in ("Metric", "---"):
            metrics[m.group(1)] = m.group(2)
    return metrics


def eval_value(metrics: dict, prefix: str) -> tuple[str, str]:
    """(label, value) for the first metric whose name starts with prefix (labels carry the threshold)."""
    for k, v in metrics.items():
        if k.startswith(prefix):
            return k, v
    return prefix, "–"


# ---- sections -------------------------------------------------------------------------
def flow_svg(counts: dict) -> str:
    """Data flow QuickBooks -> raw -> mapping -> dbt -> metrics, each box with its real count."""
    steps = [("QuickBooks", counts["companies"]), ("Raw warehouse", counts["raw"]),
             ("COA mapping", counts["mapping"]), ("dbt models + tests", counts["dbt"]),
             ("Metrics", counts["metrics"])]
    w, h, gap = 170, 74, 34
    parts = []
    for i, (title, sub) in enumerate(steps):
        x = i * (w + gap)
        parts.append(f'<rect x="{x}" y="1" width="{w}" height="{h}" rx="10" class="box"/>'
                     f'<text x="{x + w/2}" y="32" class="t1">{esc(title)}</text>'
                     f'<text x="{x + w/2}" y="54" class="t2">{esc(sub)}</text>')
        if i < len(steps) - 1:
            ax = x + w + 4
            parts.append(f'<path d="M{ax} {h/2+1} h{gap-12}" class="arrow" marker-end="url(#head)"/>')
    width = len(steps) * w + (len(steps) - 1) * gap
    return (f'<svg viewBox="0 0 {width} {h+2}" role="img" aria-label="Data flow">'
            '<defs><marker id="head" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
            'orient="auto"><path d="M0 0 L10 5 L0 10 z" class="arrowhead"/></marker></defs>'
            + "".join(parts) + "</svg>")


def main():
    con = duckdb.connect(DB, read_only=True)
    q = lambda sql, params=None: con.execute(sql, params or []).fetchall()  # noqa: E731
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    entities = {e: (name, cur) for e, name, cur in q(
        "select entity_id, entity_name, functional_currency from reference.entities order by entity_id desc")}
    mode = (q("select arg_max(mode, finished_at) from raw.sync_runs")[0][0]) or "?"
    tests = load_tests()
    timing = json.loads(TIMING.read_text()) if TIMING.exists() else None
    has_metrics = q("""select count(*) from information_schema.tables
                       where table_schema = 'marts' and table_name = 'mtr_monthly_metrics'""")[0][0]

    # ---- sync health
    sync = q("""select entity_id, stream, count(*), count(*) filter (where status = 'success'),
                       max(finished_at) filter (where status = 'success'), arg_max(status, finished_at)
                from raw.sync_runs group by 1, 2 order by 1 desc, 2""")
    sync_total, sync_ok = sum(r[2] for r in sync), sum(r[3] for r in sync)

    # ---- mapping (accounts with activity, plus the review reason from the mapping seed)
    mapping = q("""
        with activity as (
            select entity_id, account_id, any_value(account_name) as account_name,
                   any_value(standard_category) as standard_category, any_value(mapping_method) as method,
                   any_value(mapping_confidence) as confidence, any_value(mapping_status) as status,
                   sum(amount_usd) as activity_usd
            from intermediate.int_gl_usd where line_source = 'quickbooks' group by 1, 2)
        select a.*, m.reason from activity a
        left join staging.stg_coa_mapping m using (entity_id, account_id)
        order by a.status = 'approved', a.activity_usd desc""")
    n_review = sum(r[6] == "needs_review" for r in mapping)

    # ---- P&L and bridge
    months, metrics, pnl, bridge, bridge_check = [], {}, {}, {}, None
    if has_metrics:
        months = [r[0] for r in q("select period from marts.mtr_monthly_metrics order by period desc limit 3")][::-1]
        cols = "revenue, cost_of_revenue, gross_profit, gross_margin_pct, operating_expenses, operating_income, net_income"
        metrics = {r[0]: dict(zip(cols.split(", "), r[1:])) for r in q(
            f"select period, {cols} from marts.mtr_monthly_metrics where period in (select unnest(?))", [months])}
        for period, group, cat, impact in q("""
                select period, pnl_group, standard_category, net_income_impact_usd
                from marts.fct_pnl_consolidated_monthly where period in (select unnest(?))""", [months]):
            pnl.setdefault((group, cat), {})[period] = impact
        latest = months[-1]
        for e, ic, rev, opex, ni in q("""
                select entity_id, is_intercompany,
                       sum(amount_usd) filter (where pnl_group = 'Revenue'),
                       sum(amount_usd) filter (where pnl_group = 'OpEx'),
                       sum(net_income_impact_usd)
                from marts.fct_pnl_entity_monthly where period = ? group by 1, 2""", [latest]):
            b = bridge.setdefault(e, {"rev": 0, "opex": 0, "ni": 0, "ic_rev": 0, "ic_opex": 0, "ic_ni": 0})
            pre = "ic_" if ic else ""
            b[pre + "rev"] += rev or 0
            b[pre + "opex"] += opex or 0
            b[pre + "ni"] += ni or 0
        bridge_check = q("""select revenue_consolidated, opex_consolidated, net_income_consolidated
                            from marts.fct_consolidation_bridge where period = ?""", [latest])
    counts = {
        "companies": f"{len(entities)} companies",
        "raw": f"{q('select count(*) from raw.qbo_accounts')[0][0]} accounts · "
               f"{q('select count(*) from raw.qbo_pnl_monthly')[0][0]} P&L rows",
        "mapping": f"{len(mapping)} mapped · {n_review} to review",
        "dbt": f"{tests['counts'].get('pass', 0)}/{sum(tests['counts'].values())} checks pass",
        "metrics": f"{q('select count(*) from marts.mtr_monthly_metrics')[0][0] if has_metrics else 0} months",
    }
    con.close()

    # ================= render =================
    trusted = has_metrics and not tests["failing"] and all(
        all(s == "pass" for s in st) and st for st in tests["groups"].values())
    latest = months[-1] if months else None
    m_latest = metrics.get(latest, {})
    verdict = (f"Trusted: every reconciliation, consolidation, mapping and FX check passes."
               if trusted else f"Not trusted yet: {len(tests['failing'])} check(s) failing "
                               f"({', '.join(tests['failing']) or 'metrics not built'}).")
    if n_review:
        verdict += f" {n_review} account mapping(s) wait for a human before sign-off."

    tiles = [
        ("Time to first trusted P&L", f"{timing['total_seconds']:.0f} s" if timing else "–", f"{mode} mode"),
        ("Checks passing", counts["dbt"].replace(" checks pass", ""),
         f"{tests['counts'].get('warn', 0)} warning, {len(tests['failing'])} failing"),
        ("Sync success", f"{sync_ok}/{sync_total}", "stream runs"),
        (f"Revenue · {month_label(latest)}" if latest else "Revenue", money(m_latest.get("revenue")), "consolidated, USD"),
        ("Gross margin", f"{m_latest.get('gross_margin_pct') or 0:.1f}%" if m_latest else "–", "after COGS"),
        ("Net income", money(m_latest.get("net_income")), "after intercompany elimination"),
    ]
    tiles_html = "".join(f'<div class="tile"><div class="label">{esc(a)}</div><div class="value">{esc(b)}</div>'
                         f'<div class="sub">{esc(c)}</div></div>' for a, b, c in tiles)

    # health scorecard
    sync_rows = []
    for e, stream, total, ok, last, status in sync:
        age = f"{(now - last).total_seconds() / 3600:.1f} h ago" if last else "never"
        sync_rows.append([esc(f"{entities.get(e, (e,))[0]} ({e.upper()})"), esc(stream.replace("_", " ")),
                          f"{ok}/{total}", pill(status == "success", status), esc(age)])
    group_rows = []
    for g, statuses in tests["groups"].items():
        ok = bool(statuses) and all(s == "pass" for s in statuses)
        group_rows.append([esc(g), pill(ok, "pass" if ok else (", ".join(statuses) or "not run"))])
    other = ", ".join(f"{v} {k}" for k, v in sorted(tests["counts"].items()))

    # P&L: group headers, category lines, subtotals from the metrics layer
    pnl_html = "<p class='muted'>Metrics not built: dbt stopped before the marts (see checks above).</p>"
    if months:
        order = [("Revenue", None), ("COGS", ("Gross profit", "gross_profit")),
                 ("OpEx", ("Operating income", "operating_income")), ("Other", None), ("Tax", ("Net income", "net_income"))]
        rows, classes = [], []
        for group, subtotal in order:
            cats = sorted({c for (g, c) in pnl if g == group and "Intercompany" not in c})
            for c in cats:
                rows.append([esc(c)] + [money(pnl[(group, c)].get(m)) for m in months])
                classes.append("")
            if group == "Revenue":
                rows.append(["Revenue"] + [money(metrics[m]["revenue"]) for m in months])
                classes.append("subtotal")
            if subtotal:
                rows.append([subtotal[0]] + [money(metrics[m][subtotal[1]]) for m in months])
                classes.append("subtotal" if subtotal[1] != "net_income" else "total")
        pnl_html = table(["Consolidated, USD"] + [month_label(m) for m in months], rows, row_classes=classes)

    # Bridge: each company's own books (USD) - intercompany = group
    bridge_html = ""
    if bridge:
        ents = [e for e in entities if e in bridge]
        def line(label, key):
            own = [bridge[e][key] + bridge[e]["ic_" + key] for e in ents]
            elim = -sum(bridge[e]["ic_" + key] for e in ents)
            return [esc(label)] + [money(v) for v in own] + [money(elim), f"<b>{money(sum(own) + elim)}</b>"]
        headers = ([f"{month_label(latest)}, USD"] + [f"{entities[e][0]} ({e.upper()}, {entities[e][1]})" for e in ents]
                   + ["Intercompany eliminated", "Group"])
        bridge_html = table(headers, [line("Revenue", "rev"), line("Operating expenses", "opex"),
                                      line("Net income", "ni")])
        if bridge_check:
            rev_c, opex_c, ni_c = bridge_check[0]
            group_vals = [sum(bridge[e][k] for e in ents) for k in ("rev", "opex", "ni")]
            ties = all(abs(a - b) < 0.01 for a, b in zip(group_vals, (rev_c, opex_c, ni_c)))
            bridge_html += (f'<p class="muted">{pill(ties, "ties" if ties else "does not tie")} '
                            "Group column matches the consolidated P&L (dbt model fct_consolidation_bridge). "
                            "Intercompany fees are revenue for one company and cost for the other, so they "
                            "cancel out and group net income is unchanged.</p>")

    # Mapping table: review queue first, then by money moved
    map_rows, map_classes = [], []
    for e, acc_id, name, cat, method, conf, status, activity, reason in mapping:
        conf_pct = round((conf or 0) * 100)
        bar = f'<span class="nowrap"><span class="bar"><span style="width:{conf_pct}%"></span></span> {conf or 0:.2f}</span>'
        reason_short = (reason or "").split(";")[0]
        map_rows.append([esc(e.upper()), esc(name), esc(cat), esc(method), bar,
                         pill(status == "approved" or None, status.replace("_", " ")),
                         money(activity, parens=False), f'<span class="muted">{esc(reason_short[:70])}</span>'])
        map_classes.append("review" if status != "approved" else "")
    mapping_html = table(["Entity", "Account", "Standard category", "Method", "Confidence", "Status",
                          "Activity (USD)", "Why"], map_rows, numeric_from=99, row_classes=map_classes)

    # Eval before/after
    before, after = parse_eval(EVAL_BEFORE), parse_eval(EVAL_AFTER)
    eval_rows = []
    for prefix in ("Overall accuracy", "Auto-approved", "Accuracy of auto-approved", "Sent to human review"):
        lb, vb = eval_value(before, prefix)
        la, va = eval_value(after, prefix)
        thr = lambda lab: (re.search(r">= ([\d.]+)", lab).group(1) if ">=" in lab else None)  # noqa: E731
        label = prefix + (f" (threshold {thr(lb)} → {thr(la)})" if thr(lb) and thr(la) else "")
        strong = prefix == "Accuracy of auto-approved"
        eval_rows.append([f"<b>{esc(label)}</b>" if strong else esc(label), esc(vb),
                          f"<b>{esc(va)}</b>" if strong else esc(va)])
    eval_html = table(["60 labelled accounts", "Before: self-reported confidence", "After: logprob confidence"],
                      eval_rows) if before and after else "<p class='muted'>Run make eval to produce results.</p>"

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Onboarding results</title>
<style>
:root {{ --bg:#fafaf9; --card:#ffffff; --text:#1c1917; --muted:#78716c; --line:#e7e5e4; --accent:#0f766e;
        --ok-bg:#dcfce7; --ok:#166534; --warn-bg:#fef3c7; --warn:#92400e; --bad-bg:#fee2e2; --bad:#991b1b; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0c0a09; --card:#1c1917; --text:#f5f5f4; --muted:#a8a29e;
        --line:#292524; --accent:#2dd4bf; --ok-bg:#14532d; --ok:#bbf7d0; --warn-bg:#78350f; --warn:#fde68a;
        --bad-bg:#7f1d1d; --bad:#fecaca; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
main {{ max-width:1080px; margin:0 auto; padding:32px 16px 64px; }}
h1 {{ font-size:26px; margin:0 0 4px; letter-spacing:-0.01em; }}
h2 {{ font-size:17px; margin:36px 0 4px; }}
.lead {{ color:var(--muted); margin:0 0 4px; font-size:14px; }}
.muted {{ color:var(--muted); font-size:13px; }}
.verdict {{ margin:20px 0; padding:14px 16px; border-radius:10px; font-weight:600;
           background:{'var(--ok-bg)' if trusted else 'var(--bad-bg)'}; color:{'var(--ok)' if trusted else 'var(--bad)'}; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; }}
.tile {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
.tile .label {{ color:var(--muted); font-size:12px; }}
.tile .value {{ font-size:22px; font-weight:650; font-variant-numeric:tabular-nums; margin:2px 0; }}
.tile .sub {{ color:var(--muted); font-size:11px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; margin-top:10px; }}
.grid2 {{ display:grid; grid-template-columns:1.4fr 1fr; gap:10px; }}
@media (max-width:760px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
.scroll {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:13.5px; font-variant-numeric:tabular-nums; }}
th {{ text-align:left; color:var(--muted); font-weight:500; font-size:12px; border-bottom:1px solid var(--line); padding:6px 8px; white-space:nowrap; }}
td {{ border-bottom:1px solid var(--line); padding:6px 8px; vertical-align:top; }}
.num {{ text-align:right; white-space:nowrap; }}
tr.subtotal td {{ font-weight:600; border-top:1px solid var(--muted); }}
tr.total td {{ font-weight:700; border-top:2px solid var(--text); }}
tr.review td {{ background:color-mix(in srgb, var(--warn-bg) 40%, transparent); }}
.pill {{ display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px; font-weight:600; white-space:nowrap; }}
.pill.ok {{ background:var(--ok-bg); color:var(--ok); }} .pill.warn {{ background:var(--warn-bg); color:var(--warn); }}
.pill.bad {{ background:var(--bad-bg); color:var(--bad); }}
.bar {{ display:inline-block; width:44px; height:6px; border-radius:3px; background:var(--line); vertical-align:middle; }}
.bar span {{ display:block; height:100%; border-radius:3px; background:var(--accent); }}
svg {{ width:100%; height:auto; display:block; }}
svg .box {{ fill:var(--card); stroke:var(--accent); stroke-width:1.5; }}
svg .t1 {{ fill:var(--text); font-size:15px; font-weight:600; text-anchor:middle; }}
svg .t2 {{ fill:var(--muted); font-size:12px; text-anchor:middle; }}
svg .arrow {{ stroke:var(--muted); stroke-width:1.5; fill:none; }} svg .arrowhead {{ fill:var(--muted); }}
.mapping {{ max-height:520px; overflow:auto; }}
.nowrap {{ white-space:nowrap; }}
</style></head><body><main>
<h1>Acme Group: onboarding results</h1>
<p class="lead">From QuickBooks to a consolidated, reconciled P&amp;L · {esc(mode)} data ·
generated {now:%Y-%m-%d %H:%M} UTC</p>
<div class="verdict">{esc(verdict)}</div>
<div class="tiles">{tiles_html}</div>

<h2>How the data flows</h2>
<p class="muted">Each box shows what this run actually processed.</p>
<div class="card">{flow_svg(counts)}</div>

<h2>Health scorecard</h2>
<div class="grid2">
  <div class="card">{table(["Company", "Stream", "Success", "Last run", "Freshness"], sync_rows, numeric_from=2)}</div>
  <div class="card">{table(["Check group", "Result"], group_rows)}<p class="muted">All dbt tests: {esc(other)}.
  Warnings are informational (e.g. mappings waiting for review).</p></div>
</div>

<h2>Consolidated P&amp;L</h2>
<p class="muted">USD at monthly average FX rates, intercompany eliminated. Costs in brackets.</p>
<div class="card">{pnl_html}</div>

<h2>Consolidation bridge</h2>
<p class="muted">How the two companies' books add up to the group number.</p>
<div class="card">{bridge_html or "<p class='muted'>Not available.</p>"}</div>

<h2>Chart of accounts mapping</h2>
<p class="muted">Every account with activity, mapped to the standard chart of accounts. Review queue first
(highlighted), then by money moved. Revenue always gets human review on first mapping.</p>
<div class="card mapping">{mapping_html}</div>

<h2>AI mapper eval</h2>
<p class="muted">Gold set of 60 labelled US and UK accounts. The number that matters is accuracy of
auto-approved mappings: those reach the CFO without review.</p>
<div class="card">{eval_html}</div>
</main></body></html>
"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page)
    print(f"Saved {OUT} ({len(page) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
