# Session 10 pre-work: hybrid search and reranking, measured

Reproduce: `docker compose up -d --wait estimator-postgres && uv run alembic upgrade head`, ingest the corpus
(`uv run python scripts/query_examples.py` with the API up), then `uv run python -m evals.retrieval.run --repeats 10`
(billed: one embedding call per golden query). Raw output of the last run: [RESULTS.md](RESULTS.md).

## Setup

- Corpus: `data/budgets_sample.json`, 17 budgets, 60 chunks (one per component), **English** text, so the
  `tsvector` column (migration 0004) uses the `english` text search configuration.
- Vector branch: `text-embedding-3-small`, cosine k-NN on the HNSW `halfvec` index (migration 0003).
- Lexical branch: `content_tsv @@ tsquery` with OR semantics (`plainto_tsquery` with `&` turned into `|`), ranked by
  `ts_rank_cd`, GIN index `chunks_content_tsv_idx`.
- Fusion: Reciprocal Rank Fusion, `RRF_K=60`, 1-based ranks, each branch recalls 50.
- Reranker: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` on CPU (Apple Silicon laptop), recall 50, keep 5.
- Golden set: [golden_set.json](golden_set.json), 5 project descriptions, relevant budgets labelled by hand after
  reading every component. Deliberate traps: `BUD-2024-008` (fashion returns) for the fashion store query, and
  `BUD-2024-005` (e-commerce checkout) for the payments query.
- Precision@5 at chunk level = top-5 chunks whose budget is relevant. Some queries have a single relevant budget with
  4 chunks, so the best possible mean is **0.92**. Budget-level P@5 = relevant budgets / distinct budgets in the top 5.
- Latency = retrieval + rerank, median of 10 warm repeats per query. Query embedding (same for every configuration)
  and the reranker cold load (~4.9 s, once per process) are excluded.

## Results

| Config | Search | Reranking | P@5 (chunk) | P@5 (budget) | Median latency | p95 latency |
|---|---|---|---|---|---|---|
| A | Vector | No | 0.80 | 0.57 | 4.0 ms | 4.7 ms |
| B | Hybrid | No | 0.80 | 0.57 | 5.1 ms | 5.7 ms |
| C | Vector | Yes | **0.88** | **0.73** | 653 ms | 692 ms |
| D | Hybrid | Yes | **0.88** | **0.73** | 665 ms | 716 ms |

What the per-query breakdown shows:

- **Hybrid alone breaks even, by compensation.** It fixes q1 (the lexical branch pulls `BUD-2024-017` and pushes
  out the fashion returns trap) but hurts q5: "checkout"/"merchants" pull the e-commerce budget into a payments query.
  The lexical branch rewards shared words, so it causes the same "close but useless" mistake it was meant to fix.
- **Reranking is the only real gain**: +0.08 chunk P@5 (+0.17 at budget level), from q1 and q4. In q4 it brings in the
  energy-grid telemetry budget, which neither k-NN nor BM25-style ranking placed in the top 5.
- **C equals D on every query.** With recall 50 over a 60-chunk corpus, the cross-encoder sees almost the whole
  corpus, so a better recall stage cannot matter yet. Hybrid recall only starts to pay off when the corpus is much
  bigger than the recall width.
- Latency: the cross-encoder scores 50 pairs per query on CPU, about 650 ms, versus about 5 ms for either retrieval
  path. A few runs dropped to about 230 ms, which is CPU scheduling noise, not a different code path. With 60 rows
  the planner sequential-scans `chunks` instead of using either index; the indexes are for the corpus to come.

## Conclusion

I would use **configuration C (vector + reranking)** in this project. It ties for the best precision, and it is
simpler than D because it drops the lexical branch, which brings no gain and one regression at this corpus size.
The reranking cost is about 650 ms. The estimation call that consumes these chunks takes several seconds of LLM
generation, so reranking adds a few percent to the user's wait. In exchange, the estimate rests on genuinely
comparable budgets instead of neighbours by vocabulary, which is the whole point of the context. So yes, the gain
justifies the latency **for this use case**: it is a few-requests-per-session estimation tool, not an
autocomplete. Two caveats keep this honest. First, five queries over 17 budgets is a small sample: q1 and q4 alone
produce the whole gain, so this is a direction, not a proof. Second, the answer should be revisited when the corpus
grows. At that point the recall stage matters again (hybrid helps with exact terms such as PSD2, HL7/FHIR or MQTT),
and `RERANK_RECALL_K` can drop to 20 to roughly halve the reranking cost.
