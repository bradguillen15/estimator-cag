# Retrieval evaluation: precision@5 and latency

5 golden queries, 10 repeats per query and configuration. Query embeddings are computed once per query and excluded from the latency (latency = retrieval + rerank only).
Reranker cold load (excluded from latencies): 4870 ms.

| Config | Search | Rerank | Mean P@5 chunk | Mean P@5 budget | Median latency ms | p95 latency ms |
|---|---|---|---|---|---|---|
| A | vector | no | 0.800 | 0.567 | 4.0 | 4.7 |
| B | hybrid | no | 0.800 | 0.567 | 5.1 | 5.7 |
| C | vector | yes | 0.880 | 0.733 | 652.7 | 692.2 |
| D | hybrid | yes | 0.880 | 0.733 | 664.6 | 716.0 |

Mean maximum achievable chunk P@5 over the golden set: 0.920.

## Per query

| Query | Config | P@5 chunk | Max P@5 | P@5 budget | Median ms | Top budgets |
|---|---|---|---|---|---|---|
| q1 | A | 0.80 | 1.00 | 0.50 | 4.1 | BUD-2024-005, BUD-2024-005, BUD-2024-005, BUD-2024-005, BUD-2024-008 |
| q1 | B | 1.00 | 1.00 | 1.00 | 5.2 | BUD-2024-005, BUD-2024-005, BUD-2024-005, BUD-2024-005, BUD-2024-017 |
| q1 | C | 1.00 | 1.00 | 1.00 | 227.6 | BUD-2024-005, BUD-2024-005, BUD-2024-005, BUD-2024-005, BUD-2024-017 |
| q1 | D | 1.00 | 1.00 | 1.00 | 668.7 | BUD-2024-005, BUD-2024-005, BUD-2024-005, BUD-2024-005, BUD-2024-017 |
| q2 | A | 0.80 | 0.80 | 0.50 | 4.0 | BUD-2024-001, BUD-2024-001, BUD-2024-001, BUD-2024-001, BUD-2024-003 |
| q2 | B | 0.80 | 0.80 | 0.50 | 5.2 | BUD-2024-001, BUD-2024-001, BUD-2024-001, BUD-2024-001, BUD-2024-016 |
| q2 | C | 0.80 | 0.80 | 0.50 | 652.7 | BUD-2024-001, BUD-2024-001, BUD-2024-001, BUD-2024-001, BUD-2024-016 |
| q2 | D | 0.80 | 0.80 | 0.50 | 660.2 | BUD-2024-001, BUD-2024-001, BUD-2024-001, BUD-2024-001, BUD-2024-016 |
| q3 | A | 0.80 | 0.80 | 0.50 | 3.9 | BUD-2024-009, BUD-2024-009, BUD-2024-009, BUD-2024-009, BUD-2024-010 |
| q3 | B | 0.80 | 0.80 | 0.50 | 5.1 | BUD-2024-009, BUD-2024-009, BUD-2024-009, BUD-2024-009, BUD-2024-010 |
| q3 | C | 0.80 | 0.80 | 0.50 | 237.0 | BUD-2024-009, BUD-2024-009, BUD-2024-009, BUD-2024-009, BUD-2024-010 |
| q3 | D | 0.80 | 0.80 | 0.50 | 679.6 | BUD-2024-009, BUD-2024-009, BUD-2024-009, BUD-2024-009, BUD-2024-010 |
| q4 | A | 0.60 | 1.00 | 0.33 | 4.2 | BUD-2024-013, BUD-2024-013, BUD-2024-013, BUD-2024-014, BUD-2024-010 |
| q4 | B | 0.60 | 1.00 | 0.33 | 4.8 | BUD-2024-013, BUD-2024-013, BUD-2024-013, BUD-2024-010, BUD-2024-003 |
| q4 | C | 0.80 | 1.00 | 0.67 | 654.5 | BUD-2024-013, BUD-2024-013, BUD-2024-013, BUD-2024-015, BUD-2024-016 |
| q4 | D | 0.80 | 1.00 | 0.67 | 664.6 | BUD-2024-013, BUD-2024-013, BUD-2024-013, BUD-2024-015, BUD-2024-016 |
| q5 | A | 1.00 | 1.00 | 1.00 | 3.8 | BUD-2024-003, BUD-2024-003, BUD-2024-003, BUD-2024-003, BUD-2024-006 |
| q5 | B | 0.80 | 1.00 | 0.50 | 5.0 | BUD-2024-003, BUD-2024-003, BUD-2024-003, BUD-2024-003, BUD-2024-005 |
| q5 | C | 1.00 | 1.00 | 1.00 | 654.7 | BUD-2024-003, BUD-2024-003, BUD-2024-003, BUD-2024-003, BUD-2024-006 |
| q5 | D | 1.00 | 1.00 | 1.00 | 661.4 | BUD-2024-003, BUD-2024-003, BUD-2024-003, BUD-2024-003, BUD-2024-006 |
