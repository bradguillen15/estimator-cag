#!/usr/bin/env python3
"""Semantic-search smoke test against the persisted corpus (session 8).

Where ``compare.py`` measured the similarity of two loose texts, this script exercises the real retrieval path
over HTTP (``POST /embeddings/ingest`` and ``POST /search``) with five queries that probe the corpus from
different angles: direct match, semantic reformulation, out of domain, ambiguous and very specific.

Idempotent: it first ingests ``data/budgets_sample.json`` (one document per budget); budgets already persisted
answer 409 and are skipped, so re-running it never duplicates data. Real, billed embedding calls.

Usage::

    # API container (compose profile "api"), schema migrated:
    docker compose --profile api up -d --build estimator
    docker compose run --rm estimator alembic upgrade head
    docker compose run --rm estimator python scripts/query_examples.py

    # or from the host, with the API on 127.0.0.1:8000 (pnpm dev):
    uv run python scripts/query_examples.py

The base URL comes from ``ESTIMATOR_BASE_URL`` when set; otherwise the script probes the host URL and the
compose service name with ``GET /health``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = ROOT / "data" / "budgets_sample.json"

CANDIDATE_BASE_URLS = ("http://127.0.0.1:8000", "http://estimator:8000")

# Five angles on the same corpus (see the session 8 exercise statement).
QUERIES: list[tuple[str, str]] = [
    ("Known direct component (sanity check)", "REST API development with JWT authentication for financial sector"),
    (
        "Semantic reformulation (same idea, different vocabulary)",
        "secure backend service with token-based access control for banking applications",
    ),
    ("Different domain (should not be in the corpus)", "mobile application for restaurant reservations"),
    ("Ambiguous query (no dominant match)", "integration with external system"),
    (
        "Very specific query (precise technical vocabulary)",
        "migration from monolith to microservices architecture using Kubernetes",
    ),
]

TOP_K = 5
CONTENT_PREVIEW_CHARS = 120


def resolve_base_url(client: httpx.Client) -> str:
    """Honour ``ESTIMATOR_BASE_URL``; otherwise probe the usual candidates."""
    explicit = os.environ.get("ESTIMATOR_BASE_URL")
    for base_url in (explicit,) if explicit else CANDIDATE_BASE_URLS:
        try:
            if client.get(f"{base_url}/health").status_code == 200:
                return base_url
        except httpx.TransportError:
            continue
    print("ERROR: no estimator API reachable. Start it or set ESTIMATOR_BASE_URL.", file=sys.stderr)
    raise SystemExit(1)


def ingest_corpus(client: httpx.Client, base_url: str) -> None:
    """One document per budget; a 409 means it is already ingested."""
    budgets = json.loads(CORPUS_PATH.read_text())
    created = skipped = 0
    for budget in budgets:
        response = client.post(
            f"{base_url}/embeddings/ingest",
            json={
                "source_path": f"data/budgets_sample.json::{budget['budget_id']}",
                "document_type": "historical_budget",
                "content": budget,
            },
        )
        if response.status_code == 200:
            created += 1
        elif response.status_code == 409:
            skipped += 1
        else:
            print(
                f"ERROR ingesting {budget['budget_id']}: {response.status_code} {response.text[:200]}",
                file=sys.stderr,
            )
            raise SystemExit(1)
    print(f"Corpus: {len(budgets)} budgets — {created} ingested, {skipped} already present.")


def run_queries(client: httpx.Client, base_url: str) -> None:
    for index, (label, query) in enumerate(QUERIES, start=1):
        response = client.post(f"{base_url}/search", json={"query": query, "k": TOP_K})
        response.raise_for_status()
        body = response.json()

        print()
        print(f"[{index}/{len(QUERIES)}] {label}")
        print(f'    query: "{query}"')
        print(f"    search_time_ms: {body['search_time_ms']}")
        print(f"    {'chunk_id':>8}  {'distance':>8}  {'chunk_type':<18}  content")
        for hit in body["results"]:
            preview = " ".join(hit["content"].split())[:CONTENT_PREVIEW_CHARS]
            print(f"    {hit['chunk_id']:>8}  {hit['distance']:>8.4f}  {hit['chunk_type']:<18}  {preview}")


def main() -> int:
    with httpx.Client(timeout=120.0) as client:
        base_url = resolve_base_url(client)
        print(f"Estimator API: {base_url}")
        ingest_corpus(client, base_url)
        run_queries(client, base_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
