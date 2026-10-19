#!/usr/bin/env python3
"""Demo: pseudonymization with Presidio (Spanish) and an in-memory mapping store.

Builds the analyzer on ``es_core_news_md`` plus the custom recognizers, then
runs a ``ConsistentPseudonymizer`` over a seed transcript and prints the result.

Usage::

    uv run python scripts/ingestion/demo_pii.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from spacy.util import is_package

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.ingestion.pii import (  # noqa: E402
    ConsistentPseudonymizer,
    InMemoryMappingStore,
    build_analyzer,
)

MODEL = "es_core_news_md"
SALT = "demo-salt"
TRANSCRIPT = ROOT / "data" / "seed" / "transcripts" / "transcripcion_2025-02-03_betanorte.txt"


def main() -> int:
    if not TRANSCRIPT.exists():
        print(f"ERROR: {TRANSCRIPT} not found")
        return 1

    # Presidio would silently download a missing model; check first instead.
    if not is_package(MODEL):
        print(
            f"The spaCy model '{MODEL}' is not installed.\n"
            f"Install it with: uv run python -m spacy download {MODEL}"
        )
        return 1
    analyzer = build_analyzer(MODEL)

    pseudo = ConsistentPseudonymizer(
        analyzer=analyzer,
        mapping_store=InMemoryMappingStore(),
        salt=SALT,
        seed=0,
    )
    result = pseudo.pseudonymize(TRANSCRIPT.read_text(encoding="utf-8"))

    print(f"Transcript: {TRANSCRIPT.name}")
    print("\n--- Pseudonymized text (first 400 chars) ---")
    print(result.pseudonymized_text[:400])

    print(f"\n--- Applied mappings ({len(result.applied)}) ---")
    for m in result.applied[:12]:
        print(f"  {m.entity_type:14} -> {m.pseudonym}")
    print("\nSame original value -> same pseudonym across the whole document.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
