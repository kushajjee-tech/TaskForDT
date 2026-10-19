"""AI-assisted chart-of-accounts mapping.

Pipeline:  rules (stage 1)  ->  LLM for the rest (stage 2)  ->  guardrails  ->  review queue

- Only new, unmapped accounts are processed; existing (and human-approved) mappings are kept.
- The LLM maps each account in its own call, picks from the standard taxonomy (JSON, temperature 0),
  and confidence = probability of the tokens that form the chosen category (from logprobs).
  Self-reported confidence is not used: the eval showed it is ~1.0 even for wrong answers.
- Guardrail: if a suggested category flips the account's direction (expense -> revenue),
  it is sent to review regardless of confidence.
- Review policy (risk-based): revenue categories always go to human review on first mapping,
  because misclassified revenue is the costliest error. Human mappings are never overwritten.
- Otherwise confidence >= AUTO_APPROVE_CONFIDENCE is auto-approved; the rest is flagged for review.

Usage:
    python -m ai.coa_mapper              # map new accounts in the warehouse
    python -m ai.coa_mapper --offline    # rules + fallback only (no API key needed)
    python -m ai.coa_mapper --mode live  # mode defaults to SOURCE_MODE; picks the mapping file
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from ai.rules import apply_rules, fallback
from ai.taxonomy import load_taxonomy

# One mapping file per source mode: account ids are only unique within one QuickBooks company,
# so sample and live mappings must never share a file. Only the sample file is committed.
MAPPING_SEEDS = {"sample": Path("dbt/seeds/coa_mapping_sample.csv"),
                 "live": Path("dbt/seeds/coa_mapping_live.csv")}
FIELDS = ["entity_id", "account_id", "account_name", "standard_category",
          "confidence", "method", "status", "reason"]
SIGN_BY_CLASSIFICATION = {"Revenue": 1, "Expense": -1}


def category_confidence(content: str, tokens, category: str) -> float:
    """Probability the model assigned to the tokens that spell out the category value.

    The response is {"category": "<value>"}. We find where <value> sits in the text, then
    multiply the probabilities of every output token that overlaps it. This is the model's
    actual uncertainty, unlike a self-reported "confidence" field, which the eval showed is
    always ~1.0 even when the answer is wrong.
    """
    match = re.search(r'"category"\s*:\s*"', content)
    if not match:
        return 0.0
    start = match.end()
    end = start + len(json.dumps(category)) - 2  # length of the JSON-escaped value, no quotes
    logprob, pos = 0.0, 0
    for t in tokens:
        t_start, pos = pos, pos + len(t.token)
        if t_start < end and pos > start:  # token overlaps the value
            logprob += t.logprob
    return math.exp(logprob)


def llm_map_one(client, account: dict, system: str, model: str) -> dict:
    """Map one account with its own small call. Returns {category, confidence, reason}."""
    item = {"account_name": account["account_name"], "full_name": account.get("fully_qualified_name"),
            "quickbooks_type": account["account_type"], "quickbooks_subtype": account.get("account_sub_type"),
            "country": account.get("country")}
    resp = client.chat.completions.create(
        model=model, temperature=0, response_format={"type": "json_object"}, logprobs=True,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": json.dumps(item)}])
    choice = resp.choices[0]
    category = json.loads(choice.message.content).get("category")
    confidence = category_confidence(choice.message.content, choice.logprobs.content, category or "")
    return {"category": category, "confidence": confidence,
            "reason": f"llm: p(category)={confidence:.2f} from token logprobs"}


def llm_map(accounts: list[dict], taxonomy: list[dict], model: str) -> dict:
    """Map accounts with one call each (run in parallel). Returns {key: {category, confidence, reason}}.

    One call per account keeps the logprobs clean: the category tokens belong to exactly one
    account, and one account's answer cannot influence another's.
    """
    from openai import OpenAI

    client = OpenAI()
    # Category name in quotes, P&L group last, so the model copies the name exactly.
    categories = "\n".join(f'- "{t["standard_category"]}": {t["description"]} (P&L group: {t["pnl_group"]})'
                           for t in taxonomy)
    system = (
        "You are an experienced financial controller. Map an account from a company's "
        "chart of accounts to exactly one category of a standard FP&A taxonomy.\n"
        "Rules: choose only from the allowed categories, spelled exactly as listed; respect the "
        "account's QuickBooks type (an expense account can never map to a revenue category); "
        "consider regional terms (e.g. UK 'Turnover' = revenue, 'Employer's NI' = payroll tax).\n\n"
        "Allowed categories:\n" + categories + '\n\nReturn JSON only: {"category": str}')
    out = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(llm_map_one, client, a, system, model): a["key"] for a in accounts}
        for future in futures:
            try:
                out[futures[future]] = future.result()
            except Exception as exc:  # noqa: BLE001 - one failed call sends that account to fallback
                print(f"  LLM call failed for {futures[future]} ({exc})")
    return out


def map_accounts(accounts: list[dict], offline: bool, model: str, threshold: float) -> list[dict]:
    """Core mapping logic, shared by the pipeline and the eval."""
    taxonomy = load_taxonomy()
    tax = {t["standard_category"]: t for t in taxonomy}
    results, pending = {}, []

    for a in accounts:  # stage 1: rules
        hit = apply_rules(a["account_name"], a["account_type"])
        if hit:
            results[a["key"]] = {"category": hit[0], "confidence": hit[1], "reason": hit[2], "method": "rule"}
        else:
            pending.append(a)

    if pending:  # stage 2: LLM (or offline fallback)
        llm_out = {}
        if not offline:
            try:
                llm_out = llm_map(pending, taxonomy, model)
            except Exception as exc:  # noqa: BLE001
                print(f"  LLM call failed ({exc}); using offline fallback for {len(pending)} accounts")
        for a in pending:
            m = llm_out.get(a["key"])
            if m:
                results[a["key"]] = {**m, "method": "llm"}
            else:
                cat, conf, why = fallback(a["account_type"])
                results[a["key"]] = {"category": cat, "confidence": conf, "reason": why, "method": "fallback"}

    out = []
    for a in accounts:  # guardrails + review routing
        r = results[a["key"]]
        status = "approved" if r["confidence"] >= threshold else "needs_review"
        if r["category"] not in tax:
            r["reason"] = f"invalid category '{r['category']}' from model; " + r["reason"]
            r["category"], r["confidence"] = fallback(a["account_type"])[:2]
            status = "needs_review"
        expected = SIGN_BY_CLASSIFICATION.get(a.get("classification"))
        if expected and tax[r["category"]]["category_sign"] != expected:
            r["reason"] = "guardrail: category direction conflicts with account type; " + r["reason"]
            status = "needs_review"
        # Risk-based review policy: every revenue mapping is checked by a human the first time,
        # whatever the confidence. Misclassified revenue is the costliest error (it moves top line,
        # gross margin and growth, the numbers a board looks at first). Human mappings are kept.
        if tax[r["category"]]["pnl_group"] == "Revenue" and r["method"] != "human":
            r["reason"] = "policy: revenue mappings always get human review; " + r["reason"]
            status = "needs_review"
        out.append({**a, **r, "status": status})
    return out


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="rules + fallback only, no LLM")
    ap.add_argument("--remap-all", action="store_true", help="ignore existing non-human mappings")
    ap.add_argument("--mode", default=os.environ.get("SOURCE_MODE", "sample"), choices=list(MAPPING_SEEDS))
    args = ap.parse_args()
    seed = MAPPING_SEEDS[args.mode]
    offline = args.offline or not os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    threshold = float(os.environ.get("AUTO_APPROVE_CONFIDENCE", "0.97"))

    con = duckdb.connect(os.environ.get("WAREHOUSE_PATH", "warehouse/finance.duckdb"), read_only=True)
    rows = con.execute("""
        select a.entity_id, a.account_id, a.name, a.fully_qualified_name, a.account_type,
               a.account_sub_type, a.classification, e.country
        from raw.qbo_accounts a
        left join (select 'us' as entity_id, 'United States' as country
                   union all select 'uk', 'United Kingdom') e using (entity_id)
        where a.classification in ('Revenue', 'Expense')
        order by 1, 2""").fetchall()
    con.close()

    current = {(r[0], r[1]): r[2] for r in rows}

    # Keep a mapping only if it is human-approved, or the same account (id and name) is still
    # in the warehouse. Otherwise it is stale: the account was renamed, deleted, or the ids
    # belong to a different company (e.g. switching from sample data to a live sandbox).
    existing = list(csv.DictReader(seed.open())) if seed.exists() else []
    if args.remap_all:
        existing = [r for r in existing if r["method"] == "human"]
    stale = [r for r in existing if r["method"] != "human"
             and current.get((r["entity_id"], r["account_id"])) != r["account_name"]]
    existing = [r for r in existing if r not in stale]
    known = {(r["entity_id"], r["account_id"]) for r in existing}
    if stale:
        print(f"  dropped {len(stale)} stale mappings (account changed or no longer exists)")

    new = [{"key": f"{r[0]}:{r[1]}", "entity_id": r[0], "account_id": r[1], "account_name": r[2],
            "fully_qualified_name": r[3], "account_type": r[4], "account_sub_type": r[5],
            "classification": r[6], "country": r[7]}
           for r in rows if (r[0], r[1]) not in known]
    print(f"COA mapping ({seed}): {len(known)} already mapped, {len(new)} new accounts "
          f"({'offline: rules + fallback' if offline else 'rules + ' + model})")

    mapped = map_accounts(new, offline, model, threshold) if new else []
    all_rows = existing + [{
        "entity_id": m["entity_id"], "account_id": m["account_id"], "account_name": m["account_name"],
        "standard_category": m["category"], "confidence": round(m["confidence"], 2),
        "method": m["method"], "status": m["status"], "reason": m["reason"].replace("\n", " ")[:200]}
        for m in mapped]
    with seed.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(all_rows, key=lambda r: (r["entity_id"], r["account_id"])))

    by = {}
    for m in mapped:
        by.setdefault((m["method"], m["status"]), 0)
        by[(m["method"], m["status"])] += 1
    for (method, status), n in sorted(by.items()):
        print(f"  {method:9s} {status:13s} {n}")
    review = [m for m in mapped if m["status"] == "needs_review"]
    for m in review:
        print(f"  REVIEW: [{m['entity_id']}] {m['account_name']} -> {m['category']} "
              f"({m['confidence']:.2f}) {m['reason'][:80]}")


if __name__ == "__main__":
    main()
