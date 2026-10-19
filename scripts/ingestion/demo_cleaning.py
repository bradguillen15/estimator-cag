#!/usr/bin/env python3
"""Demo: cleaning + Pandera validation over the seed budgets.

Loads every budget JSON from the seed corpus, runs ``clean_budget_records``
then ``validate_with_policy`` and prints the partition report. Expected: 6
files in, 5 rows after dedup (BUDGET-2024-0005 collapses), the negative
``total_amount`` row discarded.

Usage::

    uv run python scripts/ingestion/demo_cleaning.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.ingestion.cleaning import (  # noqa: E402
    clean_budget_records,
    validate_with_policy,
)

BUDGETS_DIR = ROOT / "data" / "seed" / "budgets"


def main() -> int:
    paths = sorted(BUDGETS_DIR.glob("*.json"))
    if not paths:
        print(f"ERROR: no budget JSON files under {BUDGETS_DIR}")
        return 1

    records = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    print(f"Files read: {len(records)}  ({BUDGETS_DIR})")

    df = clean_budget_records(records)
    print(f"Rows after cleaning + dedup: {len(df)}")

    result = validate_with_policy(df)
    print("\nReport:")
    for key, value in result.report.items():
        print(f"  {key}: {value}")

    if not result.discarded.empty:
        print("\nDiscarded:")
        print(result.discarded[["budget_id", "total_amount"]].to_string(index=False))
    if not result.quarantined.empty:
        print("\nQuarantined:")
        print(result.quarantined[["budget_id", "client_name"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
