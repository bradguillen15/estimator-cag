# estimator-cag

[![Coverage Status](https://coveralls.io/repos/github/bradguillen15/estimator-cag/badge.svg?branch=main)](https://coveralls.io/github/bradguillen15/estimator-cag?branch=main)

Software project effort estimator using **CAG** (Cache-Augmented Generation): curated example
estimates are injected into the system prompt, and an LLM turns a project description into a
Markdown estimate (assumptions, task breakdown, total hours, team and duration).

| Dark · Spanish response · detailed, table by phases | Light · English response · medium, line items |
|---|---|
| ![Estimator in dark mode answering in Spanish](docs/screenshots/estimator-dark-es.png) | ![Estimator in light mode answering in English](docs/screenshots/estimator-light-en.png) |

- **API:** FastAPI + LiteLLM (`app/`), JSON and SSE streaming endpoints.
- **UI:** React 19 + TypeScript + Tailwind v4 on Vite (`web/`): one conversation per session shown as a thread (your message + its estimate per turn, then a follow-up composer), with attachments, an audience selector (automatic / executive / PM / developer) and a badge with the audience each answer was framed for, a project-memory panel plus a session-memory indicator (commitments kept, running-summary size, last audience); light/dark and Español/English toggles.
- **Prompts:** versioned Jinja2 templates (`app/prompts/estimation/v3/`).

**How it works:** [open the interactive estimation flow diagram](https://htmlpreview.github.io/?https://github.com/bradguillen15/estimator-cag/blob/main/docs/architecture/estimation-flow/estimation-flow.html).

## Requirements

- Python 3.13 with [uv](https://docs.astral.sh/uv/)
- **Node 24 LTS** (`nvm use`) and **pnpm 10** (`corepack enable pnpm`). `npm install` is blocked on purpose.
- An Anthropic and/or OpenAI API key
- Docker, only if you enable a cache

## Setup

```bash
nvm use                # Node 24 from .nvmrc
uv sync                # Python dependencies
pnpm install           # JS dependencies + the pre-commit hook
cp .env.example .env   # then set your API keys (APP_ENV and LOG_LEVEL are required)
```

## Run

```bash
pnpm dev
```

Starts the API (http://127.0.0.1:8000, docs at `/docs`) and the UI (**http://localhost:5173**).
`Ctrl+C` stops both. If a cache is enabled in `.env`, it also starts Redis through Docker.
To run them separately: `pnpm dev:api` and `pnpm dev:web`.

Production-like, single process:

```bash
pnpm build                   # builds web/dist
uv run uvicorn app.main:app  # serves the API and the UI at /
```

## Configuration

Everything is set in `.env`; [`.env.example`](.env.example) lists every option with its default.

- **Models:** `LLM_MODELS` is an ordered `<provider>/<model>` list
  (e.g. `anthropic/claude-sonnet-5-5,openai/gpt-4o-mini`). The first is the primary; the rest are
  fallbacks tried when a call fails. Only the keys of the providers you list are required.
- **Guardrails:** always on. Prompt-injection attempts are rejected with **400**; emails, phones
  and IBANs are redacted before reaching the LLM. `MODERATION_ENABLED` adds OpenAI moderation.
- **Exact cache** (`CACHE_ENABLED`): reuses the answer of an identical request. Plain Redis.
- **Semantic cache** (`SEMANTIC_CACHE_ENABLED`): reuses the answer of a near-duplicate description.
  Needs Redis Stack. With `SEMANTIC_CACHE_LOG_ONLY=true` (default) it only logs would-be hits.

- **Logging:** `APP_ENV=development` prints readable console logs; `production` prints one JSON
  line per event. Each LLM call logs latency, tokens and estimated cost.

Caches are off by default and fail open: if Redis is down, requests still work, uncached.

## API

| Method | Path | Response |
|--------|------|----------|
| `GET` | `/health` | `{"status": "ok"}` |
| `POST` | `/api/v1/estimate` | `EstimationResponse` (`text`, `prompt_version`, `cache_hit`, `audience`, `audience_rule`) |
| `POST` | `/api/v1/estimate/stream` | SSE events: `token`, `done`, `error` |
| `POST` | `/api/v1/estimate/acb` | `AcbResponse` (`estimation`, `prompt_version`, `final_verdict`, `iterations`): Actor-Critic-Boss, see below |
| `GET` | `/api/v1/context` | The CAG examples in the prompt |
| `POST` | `/api/v1/sessions` | **201** `{"session_id": "<uuid4>"}` |
| `GET` | `/api/v1/sessions` | `SessionSummary[]` (sessions with at least one turn, most recent first) |
| `GET` | `/api/v1/sessions/{session_id}` | `SessionDetail` (`project_metadata`, `history_turns`, `turns`: what was typed + attachment names + estimate per turn, oldest first, capped by the history window); **404** if unknown |
| `POST` | `/api/v1/sessions/{session_id}/estimate` | `SessionEstimationResponse` (+ `project_metadata`, `history_turns`); `multipart/form-data` with attachments |
| `POST` | `/api/v1/sessions/{session_id}/estimate/acb` | `SessionAcbResponse` (session turn fields + `final_verdict`, `iterations`): same form as the session estimate, with Actor-Critic-Boss on the session prompt |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/estimate \
  -H 'Content-Type: application/json' \
  -d '{
    "description": "E-commerce web MVP with a catalog, cart and Stripe payments",
    "project_type": "web_saas",
    "detail_level": "medium",
    "output_format": "phases_table",
    "language": "en"
  }'
```

- `project_type`: `mobile_app` | `web_saas` | `internal_tool` | `data_pipeline`
- `detail_level`: `summary` | `medium` | `detailed`
- `output_format`: `phases_table` | `line_items` | `narrative`
- `language` (optional): `es` (default) | `en`
- `?prompt_version=v1` (optional, any endpoint): compare an older prompt version side by side.

Errors: invalid input **422**, guardrail rejection **400**, prompt misconfiguration **500**,
LLM provider failure **502**. In the stream, failures arrive as an `error` event.

### Sessions and attachments

A session (`POST /api/v1/sessions`) is a conversation about one project. Estimates inside it take
the same typed fields as form fields, the text as `transcript`, and optional PDF or Word files:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/sessions/$SESSION_ID/estimate \
  -F transcript='E-commerce web MVP with a catalog, cart and Stripe payments' \
  -F project_type=web_saas -F detail_level=medium -F output_format=phases_table \
  -F attachments=@spec.pdf -F attachments=@scope.docx
```

**Attachments use local text extraction** (`pypdf` for PDF, `python-docx` for `.docx`): each
file's text is appended to the transcript under `--- attachment: <name> ---`. We chose it over
sending the files to a multimodal Files API because:

- **It keeps the fallback chain working.** A file uploaded to one vendor's Files API does not
  exist for the next model in `LLM_MODELS`; plain text works with any of them.
- **The guardrails see the attachments.** An instruction hidden in a PDF (indirect prompt
  injection) is rejected, and PII in it is redacted, exactly as in the transcript.
- **Caches and RAG keep working on text**, which is also the input for chunking later on.

The cost: images and diagrams are ignored, and scanned PDFs (no text layer) are rejected with a
**400**. Limits: 5 files, 5 MB each, 60,000 extracted characters in total; `.doc`, encrypted PDFs
and other types are rejected with **400**. An unknown `session_id` is a **404**. Sessions live in
process memory: a restart forgets them.

**Actor-Critic-Boss** (`POST /estimate/acb`, same body and input guardrails as `/estimate`): the
estimate is audited by a *Critic* (a second LLM call that answers JSON: verdict `accept` |
`needs_iteration` | `reject`, plus issues with category, severity and message). A *Boss* (pure
orchestration, `services/boss.py`) re-runs the actor with a trailing `critic_feedback` prompt block
while the Critic asks for another iteration and `BOSS_MAX_ITERATIONS` (default 3, the maximum number
of actor attempts) allows it; `reject` stops at once. The last draft is always returned with
`final_verdict` (`needs_iteration` means the budget ran out with issues open) and the per-attempt
`iterations` trail. A `needs_iteration` without a critical/major issue counts as `accept`, and a
Critic failure (provider error, invalid JSON) accepts the draft and is logged. **Cost: up to
2 x `BOSS_MAX_ITERATIONS` LLM calls per request** (one when the first draft is accepted: actor +
critic). `CRITIC_MODEL` (optional `<provider>/<model>`, e.g. a cheaper one) overrides the model;
empty reuses `LLM_MODELS`. Both caches are bypassed. No UI yet.

`POST /sessions/{id}/estimate/acb` runs the same Boss on the session conversation (memory, metadata,
audience and history window in the actor prompt; the `critic_feedback` block is added on retries).
Only the final estimate is recorded as the turn (history, compression, metadata, `final_verdict` on
the turn view); drafts are discarded. Same cost: up to 2 x `BOSS_MAX_ITERATIONS` calls plus the
usual per-turn metadata/summary calls.

**Audience tier**: every estimate endpoint (and the session turn form) accepts an optional `audience`
(`executive` | `pm` | `developer` | `default`; anything else is a **422**). Without it, a pure regex
resolver (`services/audience.py`, no LLM, English and Spanish) infers it from the description in this
order: explicit value, NDA/regulatory/board/investor terms (executive), executive vocabulary, two or
more developer keywords (developer), a session team size of 2 or fewer (developer), delivery
vocabulary such as sprint or roadmap (pm), otherwise `default`. A non-default tier adds one trailing
`audience.j2` block (the `default` prompt is byte-identical to before) and is part of both cache
keys, so two tiers never share an answer. Responses carry `audience` and `audience_rule` (which rule
fired); `GET /sessions/{id}` reports `last_audience` and `last_audience_rule`.

**History** is a sliding window of the last `SESSION_MAX_TURNS` turns (default 6; a turn is a
user message plus the answer). Each call sends the system prompt, rebuilt with the current
project metadata, then the kept turns, then the new message; older turns leave as whole
pairs and are compressed instead of lost: a pair whose user message carries a commitment (NDA,
signed contract, frozen scope, locked budget, compliance regime such as GDPR/HIPAA, hard
deadline, explicit agreement; English and Spanish patterns) is kept verbatim as an *anchor*
(at most `SESSION_MAX_ANCHORS`, default 5, oldest dropped first); every other pair is folded
by a second small LLM call into a running summary capped at `SESSION_SUMMARY_MAX_CHARS`
(default 2000; a failure keeps the previous summary). Both render as one trailing block of the
system prompt (`history_memory.j2`), absent until a turn overflows the window, so the cacheable
prefix is untouched. `GET /sessions/{id}` reports `anchors_count` and `summary_chars`. The history keeps the transcript and only a reference to the attachments
(`[attachments: spec.pdf]`), not their text: replaying up to 60,000 characters on every later
call would multiply the cost, and the facts taken from them already live in the metadata.

**Project metadata** carries the project facts across turns: name, assumed team size, mentioned
technologies and agreed scope. It is injected at the end of the system prompt as a
`<project_metadata>` block (empty on the first turn), after the static prefix, so prompt caching
still applies. After each answer **a second LLM call extracts the facts as JSON** and merges them:
new values replace old ones, technologies accumulate. We chose an LLM extractor over regex
because the agreed scope is semantic, a summary of what the conversation added and removed, which
no pattern can produce; the name or the technologies alone would have fit a heuristic. The cost
is one extra call per turn. Safeguards:

- A failed extraction (provider error, invalid JSON) keeps the previous facts and never fails the
  turn.
- The facts come from user text and land in the system prompt, so every value is checked with the
  prompt-injection heuristics and length-capped before it is stored.
- Session turns skip the response caches: the cache key does not cover the metadata, so a hit
  could replay an answer built on other facts.

## Tests

```bash
pnpm test            # API (pytest) then UI (Vitest)
pnpm test:api        # API only
pnpm test:web        # UI only
pnpm lint            # ESLint
```

Tests never call a real LLM or Redis. The pre-commit hook runs the same checks as CI.
`tests/integration/` drives whole session flows over HTTP with `httpx.AsyncClient`; its fake
LLM answers from the prompt it receives, so they prove that context reaches the model and flows
across turns, not how well a real model uses it.

## Evals

A golden dataset (`evals/golden_dataset.json`: varied project types, detail levels, formats, ES and EN,
plus an insufficient-information case) is run through the real estimation pipeline and scored with
deterministic metrics: schema adherence (the production output check), total hours within the case
bounds (parsed from the Markdown total) and keyword recall.

```bash
pnpm evals                                         # all cases
uv run python -m evals.run --case mobile-delivery-detailed-en --threshold 0.8 --prompt-version v3
```

**Cost warning:** every case is a real, billed LLM call using your `.env` keys and `LLM_MODELS`.
The response caches are never used, so each run reaches the model. The command exits non-zero when
the aggregate score is below `--threshold` (default 0.8). `pytest` never runs evals.

## Project structure

```
app/            # FastAPI: routers, schemas, services (LLM, cache, guardrails), prompts
web/src/        # React UI: api client, components, hooks
tests/          # pytest
evals/          # golden dataset, metrics and CLI runner (real LLM calls; dev tool)
scripts/        # dev runner and CI scripts
docs/           # architecture diagrams, screenshots, sample descriptions
```

## Contributing

Layers, conventions, recipes, the PR flow (protected `main`, CodeRabbit) and the definition of
done live in [AGENTS.md](AGENTS.md).
