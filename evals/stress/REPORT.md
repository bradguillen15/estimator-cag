# CAG Stress Test: Report (template)

> Empirical map of where the session pipeline breaks. This is a TEMPLATE: every
> value in `_italics_` is a placeholder to replace with numbers from your own
> `results.csv`. No result has been measured yet.

## How to run

```bash
uv sync                                          # fpdf2 is a dev dependency (PDF fixtures only)
uv run python -m evals.stress.fixtures.build_pdfs   # optional: the runner builds missing PDFs itself

# Live server (recommended). Use ONE cheap model so cost is comparable:
LLM_MODELS='["openai/gpt-4o-mini"]' uv run uvicorn app.main:app &
uv run python -m evals.stress.run \
    --http http://localhost:8000 \
    --scenarios growing,pivot,contradiction \
    --attachment-sizes 0,5,20,50,100 \
    --repeats 3 \
    --latency-budget-ms 8000 \
    --cost-budget-usd 0.02 \
    --output evals/stress/results.csv
```

- Without `--http` the runner starts the app in process (`TestClient`) with the real
  providers from `settings`: **it is billed** exactly like a live run.
- `--max-turns N` caps the turns per scenario (each has 20) for a cheaper trial.
- The server's `SESSION_MAX_TURNS` (default 6) sets the history window; record it below.
- `results.csv` is git-ignored. Row count: scenarios x sizes x repeats x 20 turns, minus
  sessions aborted by an error (an error row is written with its HTTP status and message).

## Why `evals/stress/metrics.py` is separate from `evals/metrics.py`

`evals/metrics.py` scores a `(GoldenCase, Markdown answer)` pair. The stress metrics read a
`TurnObservation` (telemetry returned with each session turn) and the JSON of
`GET /api/v1/sessions/{id}`. The input types differ, so they live in their own module;
`MetricResult` is imported from `evals.metrics` so reports keep one shape. All checks are
deterministic (no LLM judge).

## Run parameters (fill in)

| Setting               | Value                          |
|-----------------------|--------------------------------|
| `LLM_MODELS`          | _e.g. `["openai/gpt-4o-mini"]`_ |
| `SESSION_MAX_TURNS`   | _6 (default)_                  |
| Scenarios             | growing, pivot, contradiction  |
| Attachment sizes (KB) | 0, 5, 20, 50, 100              |
| Repeats per cell      | 3                              |
| Latency budget        | 8000 ms                        |
| Cost budget per turn  | $0.02                          |
| Rows in `results.csv` | _n_                            |
| Wall-clock to run     | _minutes_                      |

## Facts of this implementation that shape the numbers

- **Attachments over the cap fail, they are not truncated.** `MAX_ATTACHMENTS_CHARS = 60_000`
  in `app/services/attachments.py` rejects the request with HTTP 400 (`AttachmentError`). The
  generated 100 KB PDF holds about 102,000 characters of text, so the **100 KB column measures
  a hard failure**: expect an error row on turn 1 of every such session (and therefore no
  telemetry or drift data for it). The 50 KB column (about 51,000 chars) is the largest size
  that is actually processed.
- **Caches are not used by session turns**, so `cache_hit_kind` is always `none`.
- **Memory drift** searches the fact (case-insensitive substring) in `summary`, `anchors` and
  `metadata` of `GET /sessions/{id}`, where `metadata` is every `project_metadata` value
  flattened to text. `ProjectMetadata` has no budget field (only `project_name`,
  `assumed_team_size`, `mentioned_technologies`, `agreed_scope`), so the budget facts of the
  `contradiction` profile (`30000`, `80000`) can only survive in the summary or the anchors.
  The runner tracks the fact of turn 1 (the project name, searched in `metadata`) and skips
  the check on turn 1 itself.
- `latency_ms` is the server-side wall clock of the whole turn (actor, metadata extractor and
  summarizer when turns overflowed the window); `wall_clock_ms` adds the HTTP round trip.
  `cost_usd`, `tokens_in` and `tokens_out` sum all LLM calls of the turn.

---

## 1. Summary table

One row per `(scenario, attachment_size_kb)` cell, from the runner's printed summary.

| Scenario      |  KB | n   | P50 ms | P95 ms | Total $ | Drift pass % |
|---------------|----:|-----|-------:|-------:|--------:|-------------:|
| growing       |   0 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| growing       |   5 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| growing       |  20 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| growing       |  50 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| growing       | 100 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| pivot         |   0 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| pivot         |   5 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| pivot         |  20 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| pivot         |  50 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| pivot         | 100 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| contradiction |   0 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| contradiction |   5 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| contradiction |  20 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| contradiction |  50 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |
| contradiction | 100 | _n_ | _xxx_ | _xxx_ | _x.xx_ | _xx.x_ |

> The 100 KB rows should read `n = 0` in the summary (all error rows, HTTP 400); count them
> from `results.csv` with `status_code = 400`.

## 2. Three curves (as tables)

### 2a. Latency vs context size

`tokens_in` is the proxy for how much context the model swallowed. Bucket by `tokens_in`,
take the median `latency_ms`.

| `tokens_in` bucket | Median latency (ms) | n   |
|--------------------|--------------------:|-----|
| 0-999              |              _xxx_  | _x_ |
| 1000-2999          |              _xxx_  | _x_ |
| 3000-6999          |              _xxx_  | _x_ |
| 7000-14999         |              _xxx_  | _x_ |
| 15000+             |              _xxx_  | _x_ |

### 2b. Cost accumulated vs turn index (size = 0)

Cumulative `cost_usd` per turn, averaged across repeats.

| Turn | growing $ | pivot $ | contradiction $ |
|-----:|----------:|--------:|----------------:|
|    1 |   _x.xx_  | _x.xx_  |        _x.xx_   |
|    5 |   _x.xx_  | _x.xx_  |        _x.xx_   |
|   10 |   _x.xx_  | _x.xx_  |        _x.xx_   |
|   15 |   _x.xx_  | _x.xx_  |        _x.xx_   |
|   20 |   _x.xx_  | _x.xx_  |        _x.xx_   |

### 2c. Memory drift pass rate vs turn index (size = 0)

For each turn N >= 2, did the turn-1 fact still appear in the session snapshot? Pooled across
repeats and scenarios. Look for the step when turns start leaving the `SESSION_MAX_TURNS` window.

| Turn N | Drift pass rate (%) | n   |
|-------:|--------------------:|-----|
|      2 |             _xx.x_  | _x_ |
|      5 |             _xx.x_  | _x_ |
|     10 |             _xx.x_  | _x_ |
|     15 |             _xx.x_  | _x_ |
|     20 |             _xx.x_  | _x_ |

## 3. Reading: where the CAG starts to break

**Dominant failure mode** (about 5 lines): _anchor it to the numbers above (which turn and
size the latency/cost budgets or the drift check first fail, and why)._

**What this implies for retrieval instead of injection** (about 5 lines): _cite the curves._

## 4. Claims to defend

1. My CAG starts degrading between turns ___ and ___ because ___.
2. Cost per turn grows with O(___) because each turn re-injects ___.
3. The dominant latency bottleneck is ___ because ___.
4. To cut context by 50% without losing recall, I would attack ___ first because ___.
5. Attachments beyond 60,000 extracted characters fail with HTTP 400 instead of degrading.
