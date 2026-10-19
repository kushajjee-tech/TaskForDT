"""Evaluate the COA mapper on a labelled gold set (evals/coa_gold.csv).

Reports overall accuracy, auto-approval rate, accuracy of auto-approved mappings
(the number that matters: wrong auto-approvals reach the CFO without review),
and the errors. Writes evals/results_<mode>.md.

It also calibrates the auto-approve threshold: mappings are scored once, then for each
candidate threshold we measure how many would be auto-approved and how accurate those are.
Recommended threshold: among thresholds where auto-approved accuracy >= TARGET_ACCURACY, take
those with the most automation, then the highest (most conservative) of them. When the gold
set has few errors, many thresholds tie, and we don't give away safety the eval can't justify.

Usage:
    python -m ai.eval_coa_mapper            # rules + LLM (needs OPENAI_API_KEY)
    python -m ai.eval_coa_mapper --offline  # rules + fallback baseline
    python -m ai.eval_coa_mapper --out evals/results_llm_after.md
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from dotenv import load_dotenv

from ai.coa_mapper import map_accounts

TARGET_ACCURACY = 0.98
CANDIDATE_THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.97, 0.98, 0.99, 0.995, 0.999]


def calibrate(results: list[dict]) -> tuple[list[tuple], float | None]:
    """results must come from map_accounts(threshold=0), so status reflects only the other gates
    (guardrail, revenue policy, invalid category). Returns (sweep rows, recommended threshold)."""
    eligible = [r for r in results if r["status"] == "approved"]
    rows = []
    for t in CANDIDATE_THRESHOLDS:
        auto = [r for r in eligible if r["confidence"] >= t]
        ok = sum(r["category"] == r["expected_category"] for r in auto)
        rows.append((t, len(auto), ok, ok / len(auto) if auto else None))
    passing = [row for row in rows if row[3] is not None and row[3] >= TARGET_ACCURACY]
    if not passing:
        return rows, None
    most_auto = max(row[1] for row in passing)
    return rows, max(row[0] for row in passing if row[1] == most_auto)


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out", help="where to write the results (default evals/results_<mode>.md)")
    args = ap.parse_args()
    offline = args.offline or not os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    threshold = float(os.environ.get("AUTO_APPROVE_CONFIDENCE", "0.97"))

    gold = list(csv.DictReader(Path("evals/coa_gold.csv").open()))
    accounts = [{"key": str(i), "entity_id": "eval", "account_id": str(i), **g} for i, g in enumerate(gold)]
    # Score once with no confidence threshold, then apply thresholds here (one set of API calls).
    results = map_accounts(accounts, offline, model, threshold=0.0)
    sweep, recommended = calibrate(results)
    for r in results:
        if r["status"] == "approved" and r["confidence"] < threshold:
            r["status"] = "needs_review"

    n = len(results)
    correct = [r for r in results if r["category"] == r["expected_category"]]
    auto = [r for r in results if r["status"] == "approved"]
    auto_correct = [r for r in auto if r["category"] == r["expected_category"]]
    by_method = {}
    for r in results:
        m = by_method.setdefault(r["method"], [0, 0])
        m[0] += 1
        m[1] += r["category"] == r["expected_category"]

    mode = "offline" if offline else model
    lines = [f"# COA mapper eval ({'rules + fallback' if offline else 'rules + ' + model})", "",
             "| Metric | Value |", "|---|---|",
             f"| Accounts in gold set | {n} |",
             f"| Overall accuracy | {len(correct)/n:.0%} ({len(correct)}/{n}) |",
             f"| Auto-approved (confidence >= {threshold}) | {len(auto)/n:.0%} ({len(auto)}/{n}) |",
             f"| Accuracy of auto-approved | {len(auto_correct)/max(len(auto),1):.0%} ({len(auto_correct)}/{len(auto)}) |",
             f"| Sent to human review | {n-len(auto)} |", "", "| Stage | Accounts | Accuracy |", "|---|---|---|"]
    lines += [f"| {k} | {v[0]} | {v[1]/v[0]:.0%} |" for k, v in sorted(by_method.items())]
    lines += ["", f"## Threshold calibration (target: auto-approved accuracy >= {TARGET_ACCURACY:.0%})", "",
              "| Threshold | Auto-approved | Accuracy of auto-approved |", "|---|---|---|"]
    lines += [f"| {t} | {n_auto}/{n} | {f'{acc:.1%} ({ok}/{n_auto})' if acc is not None else '-'} |"
              for t, n_auto, ok, acc in sweep]
    lines += ["", f"Recommended AUTO_APPROVE_CONFIDENCE: **{recommended}**" if recommended is not None
              else f"No threshold reaches {TARGET_ACCURACY:.0%}: keep everything in review."]
    errors = [r for r in results if r["category"] != r["expected_category"]]
    if errors:
        lines += ["", "## Errors", "", "| Account | Expected | Predicted | Conf. | Status |", "|---|---|---|---|---|"]
        lines += [f"| {r['account_name']} | {r['expected_category']} | {r['category']} | "
                  f"{r['confidence']:.2f} | {r['status']} |" for r in errors]
    report = "\n".join(lines)
    out = Path(args.out or f"evals/results_{'offline' if offline else 'llm'}.md")
    out.write_text(report + "\n")
    print(report)
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
