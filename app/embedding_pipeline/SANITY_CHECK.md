# Embedding sanity check

Model: `text-embedding-3-small` (1536 dims, default dimension).
Generated with `scripts/compare.py` (cosine computed by hand, stdlib only).
Run date: 2026-10-19.

| Pair | Text A | Text B | Cosine | Expectation |
|------|--------|--------|--------|-------------|
| A — near | "OAuth 2.0 authentication backend with JWT tokens for fintech mobile app" | "Authorization service using JSON Web Tokens for a banking application" | **0.5957** | high (> 0.6) |
| B — unrelated | "OAuth 2.0 authentication backend with JWT tokens for fintech mobile app" | "Database migration from MySQL to PostgreSQL with zero downtime" | **0.1920** | low (< 0.4) |
| C — generic | "Backend services" | "API development" | **0.5408** | no fixed expectation |

## Commentary

Pair B matches intuition: two unrelated topics land at 0.19, well under 0.4, so the model clearly separates
"auth for fintech" from "database migration".

Pair A sits just under the 0.6 guideline although both texts describe the same thing. They share almost no
words (OAuth/JWT/fintech vs Authorization/JSON Web Tokens/banking), so the match is purely semantic: a good
reminder that thresholds depend on the model and the phrasing, they are not universal constants.

Pair C is the surprise: two short, vague phrases score 0.54, almost as close as the genuinely related Pair A.
Short generic text carries little signal, so everything "backend-ish" clusters together. That is why the
chunker prepends the parent budget header (project, sector, year, tech) to each component.

The numbers match the course reference run (0.5957 / 0.1920 / 0.5407) to the fourth decimal, so the pipeline
reproduces it.
