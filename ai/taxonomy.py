"""Standard chart of accounts, read from the dbt seed so there is one source of truth."""
import csv
from pathlib import Path

SEED = Path("dbt/seeds/standard_coa.csv")


def load_taxonomy(include_intercompany: bool = False) -> list[dict]:
    rows = list(csv.DictReader(SEED.open()))
    for r in rows:
        r["category_sign"] = int(r["category_sign"])
        r["is_intercompany"] = r["is_intercompany"].lower() == "true"
    return [r for r in rows if include_intercompany or not r["is_intercompany"]]
