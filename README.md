# estimator-cag

[![Coverage Status](https://coveralls.io/repos/github/bradguillen15/estimator-cag/badge.svg?branch=main)](https://coveralls.io/github/bradguillen15/estimator-cag?branch=main)

Software project effort estimator using **CAG** (Cache-Augmented Generation): curated example
estimates are injected into the system prompt, and an LLM turns a project description into a
Markdown estimate (assumptions, task breakdown, total hours, team and duration).

| Dark · Spanish response · detailed, table by phases | Light · English response · medium, line items |
|---|---|
| ![Estimator in dark mode answering in Spanish](docs/screenshots/estimator-dark-es.png) | ![Estimator in light mode answering in English](docs/screenshots/estimator-light-en.png) |

- **API:** FastAPI + LiteLLM (`app/`), JSON and SSE streaming endpoints.
- **UI:** React 19 + TypeScript + Tailwind v4 on Vite (`web/`): one conversation per session with attachments and a project-memory panel; light/dark and Español/English toggles.
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
| `POST` | `/api/v1/estimate` | `EstimationResponse` (`text`, `prompt_version`, `cache_hit`) |
| `POST` | `/api/v1/estimate/stream` | SSE events: `token`, `done`, `error` |
| `GET` | `/api/v1/context` | The CAG examples in the prompt |
| `POST` | `/api/v1/sessions` | **201** `{"session_id": "<uuid4>"}` |
| `GET` | `/api/v1/sessions` | `SessionSummary[]` (sessions with at least one turn, most recent first) |
| `GET` | `/api/v1/sessions/{session_id}` | `SessionDetail` (`project_metadata`, `history_turns`, `last_estimate`); **404** if unknown |
| `POST` | `/api/v1/sessions/{session_id}/estimate` | `SessionEstimationResponse` (+ `project_metadata`, `history_turns`); `multipart/form-data` with attachments |

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

**History** is a sliding window of the last `SESSION_MAX_TURNS` turns (default 6; a turn is a
user message plus the answer). Each call sends the system prompt, rebuilt with the current
project metadata, then the kept turns, then the new message; older turns are dropped as whole
pairs. The history keeps the transcript and only a reference to the attachments
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

## Project structure

```
app/            # FastAPI: routers, schemas, services (LLM, cache, guardrails), prompts
web/src/        # React UI: api client, components, hooks
tests/          # pytest
scripts/        # dev runner and CI scripts
docs/           # architecture diagrams, screenshots, sample descriptions
```

## Contributing

Layers, conventions, recipes, the PR flow (protected `main`, CodeRabbit) and the definition of
done live in [AGENTS.md](AGENTS.md).
