# Session 07 pre-exercise: minimal embeddings + structural chunking pipeline

## Objective

Port the reference course branch `ai-engineering` `origin/session_07` (estimator/) into estimator-cag on
branch `session_7`: structural JSON chunker, OpenAI embedder, `POST /embeddings/ingest`, `scripts/compare.py`
and `SANITY_CHECK.md` with the three similarity pairs.

## Why

First step towards semantic search: turn the historical budgets into vectors (in memory, returned over
HTTP). Persistence (pgvector) is session 8.

## Scope

- In: `app/embedding_pipeline/` (schemas, chunker, embedder, router), `data/budgets_sample.json`,
  `scripts/compare.py`, `tiktoken` dependency, README run instructions, SANITY_CHECK.md.
- Out: other chunking strategies, model comparisons, LLM chunk enrichment, vector DB, retrieval, UI changes.

## Constraints

- User decision (2026-10-19): follow the reference **literally** (module layout, direct `openai` SDK,
  `/embeddings` prefix), even where it deviates from AGENTS.md layers. Any structural adaptation to this
  repo goes in its **own commit** so the difference from the reference stays visible.
- Commits on `session_7` per work unit (user asked for per-commit changes); Conventional Commits, no AI
  attribution, Node 24 first in PATH for the Husky hook. Push/PR are the user's decision.

## Workflow settings

- TDD: off (source: none). Runner: `uv run pytest`.
- RDD: off (per previous session docs).
- Delivery: ~1.1k lines, mostly the 620-line sample JSON; single branch.

## Tasks

- [x] T1 Port module + wiring (dependencies, main, tiktoken) with the minimum renames this repo needs (inline; `ed582d8`)
- [x] T2 Port compare.py + sample data + README/AGENTS docs (inline; `999abb9`)
- [x] T3 Run sanity pairs (billed, ~$0.000001) and write SANITY_CHECK.md (inline)

## Progress

- Branch `session_7` created from up-to-date `main`.
- Checks: `uv run pytest` green; `/health` ok; `/embeddings/ingest` in OpenAPI; live ingest of the sample
  → 200, 52 chunks, 4126 tokens, $0.00008, 1536-dim vectors; empty budgets → 422.
- Sanity pairs: A 0.5957, B 0.1920, C 0.5408 (match the reference run).
- Literal deviations kept (AGENTS.md §7 #12). Pending/user decisions: no API container for
  `docker compose exec` (README says so); deliverable branch name in the brief is `session-07/pre-exercise`
  (we use `session_7`); push/PR.
