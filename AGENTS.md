# AGENTS.md

Operating guide for AI agents and humans working on **estimator-cag**.
Read this before writing code. It defines *where* things go, *why*, and *what "done" means*.

---

## 1. What this app is

A FastAPI service that turns a **project description** (e.g. notes from a client meeting) into a
**software effort estimation**, using **CAG (Cache-Augmented Generation)**: curated historical
examples are injected into the system prompt instead of being retrieved at query time.

Single flow today (`/estimate` returns the full answer, `/estimate/stream` the same answer over SSE):

```
POST /api/v1/estimate[/stream]  →  router (get_safe_request: input guardrails)  →  EstimationService  →  exact cache → semantic cache → LLMProvider (LiteLLM)  →  output check  →  Markdown estimation
```

The interactive diagram of this flow, with file/line sources per node, is
[viewable here](https://htmlpreview.github.io/?https://github.com/bradguillen15/estimator-cag/blob/main/docs/architecture/estimation-flow/estimation-flow.html)
(source: `docs/architecture/estimation-flow/`; see §5.5 to regenerate it).

Everything in this document exists to keep that flow easy to extend (more providers, more endpoints,
more context sources) **without rewriting it**.

---

## 2. Stack and commands

| Item | Value |
|---|---|
| Python | 3.13 (`.python-version`) |
| Package manager | `uv` (lockfile: `uv.lock`) |
| Web | FastAPI + Uvicorn |
| Frontend | React 19 + TypeScript + Tailwind v4 on Vite 6 (`web/`) |
| Node | **24 LTS**, pinned in `.nvmrc` (CI reads the same file) |
| JS package manager | **pnpm 10** workspace (root + `web/`, one `pnpm-lock.yaml`). npm/yarn are blocked. |
| Config | pydantic-settings |
| LLM SDK | `litellm` (Anthropic primary + OpenAI fallback, ordered by `LLM_MODELS`) |

```bash
uv sync                                    # install deps
cp .env.example .env                       # then fill the keys
pnpm install                               # install UI deps (whole workspace)
pnpm dev                                   # run API + UI together (Ctrl+C stops both); also starts Redis (Docker) if a cache flag is enabled
uv run uvicorn app.main:app --reload       # run API (http://127.0.0.1:8000/docs)
pnpm dev:web                               # run UI only (http://localhost:5173, proxies /api → :8000)
pnpm build                                 # build UI → web/dist, served by FastAPI at /
pnpm lint                                  # ESLint (build also type-checks with tsc)
pnpm --filter estimator-web add <pkg>      # add a UI dependency (never npm install)
uv add <pkg>                               # add a dependency (never edit pyproject by hand)
```

**Never** commit `.env`. Any new setting must be added to `.env.example` with an empty or safe default
in the same commit.

---

## 3. Architecture

### 3.1 Layer map

```
app/
├── main.py              # Composition root: app, routers, middleware, exception handlers, logging boot
├── config.py            # Settings (pydantic-settings). The ONLY place that reads env vars.
├── dependencies.py      # FastAPI Depends providers (get_estimation_service) — overridable in tests
├── exceptions.py        # Domain errors (EstimationError → PromptTemplateError / LLMProviderError)
├── logging_config.py    # Structlog dual config (console / JSON) + cost helper
├── prompts/             # Jinja2 templates + loader (estimation/<version>/)
├── routers/             # HTTP layer: parse, validate, delegate, map errors to status codes
├── schemas/             # Pydantic request/response models
└── services/            # Business logic. Knows nothing about HTTP.
    ├── estimation_service.py   # Use case: render prompts, delegate to the provider
    ├── sessions.py             # Session state: sliding-window history + ProjectMetadata, in-process store
    ├── attachments.py          # PDF/.docx text extraction (pypdf, python-docx), appended to the transcript
    ├── guardrails/             # input.py (injection reject, PII redaction, moderation hook) · output.py (answer structure check)
    ├── cache/                  # base.py (ResponseCache Protocol, key) · redis_cache.py (exact) · semantic.py (redisvl) · factory.py
    └── llm/                    # base.py (Protocols) · litellm.py / moderation.py / embeddings.py (the only users of the LLM SDK) · factory.py

tests/                   # pytest: prompts, schemas, provider (patched litellm.completion), service, routes

web/src/                 # React UI — talks to the API over HTTP only, never imports Python
├── api/                 # client.ts (fetch + SSE parser) and types.ts (mirror of app/schemas)
├── components/          # Presentational pieces; no fetch calls here
└── hooks/               # useEstimation (request lifecycle), useTheme (light/dark)
```

### 3.2 The dependency rule

Dependencies point **inward and downward only**:

```
main → routers → services → context / config
```

- A **router** may import services and schemas. It must never build a prompt or call an SDK.
- A **service** must never import `fastapi`, never raise `HTTPException`, never see a `Request`.
- **web/** reaches the backend only through `web/src/api/client.ts`. Components never call `fetch`.
  `types.ts` mirrors `app/schemas/`: change both in the same commit.
- **config.py** imports nothing from the app.

If you catch yourself importing "upward", the abstraction is in the wrong layer — move it, don't
patch around it.

### 3.3 Where each concern lives

| Concern | Home | Rule |
|---|---|---|
| HTTP status codes | `routers/` | Only place that knows about 400/502/… |
| Input shape validation | `schemas/` (Pydantic) | Declarative constraints, not `if` statements in the router |
| Domain rules / errors | `services/` | Raise domain exceptions, let the router translate them |
| Prompt text & assembly | `prompts/` + `prompts/loader.py` | Never inline a prompt string in a router |
| Provider SDK calls | `services/llm/` | `litellm` is imported only under `app/services/llm/` (completion, moderation, embeddings); a non-LiteLLM backend would get its own file there |
| Cache backends | `services/cache/` | `redis` / `redisvl` are imported only under `app/services/cache/`; callers see the `ResponseCache` / `SemanticCache` Protocols |
| Input guardrails | `services/guardrails/input.py` | Run in the `get_safe_request` dependency (see §5.1), never inside a streaming handler |
| Env vars & secrets | `config.py` | `os.getenv` anywhere else is a bug |

---

## 4. Principles, applied to *this* codebase

Generic principle statements are useless. These are the concrete rules they translate to here.

### 4.1 SRP — one reason to change per unit

`LLMService` currently does three jobs: build the prompt, hold provider config, and call the LLM
SDK. Three reasons to change. Split as work lands:

- **Prompt assembly** → `app/prompts/loader.py` (changes when prompt wording changes)
- **Provider call** → `app/services/llm/litellm.py` (changes when the SDK changes)
- **Use case orchestration** → `app/services/estimation_service.py` (changes when the business flow changes)

A router handler stays under ~15 lines. If it grows, the logic belongs in a service.

### 4.2 OCP — open for extension, closed for modification

Adding another LLM vendor must not require editing the estimation logic.

Structure:

```
app/services/llm/
├── base.py       # LLMProvider / StreamingLLMProvider Protocols (the abstraction)
├── litellm.py    # LiteLLMProvider (ordered model list with fallback; the only SDK user)
└── factory.py    # get_llm_provider(settings) -> StreamingLLMProvider
```

```python
# app/services/llm/base.py
from typing import Protocol

class LLMProvider(Protocol):
    name: str
    model: str
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...
```

LiteLLM already speaks to many vendors, so a new vendor = its `<prefix>` → API-key mapping in
`factory.py` plus a key setting. Zero edits to the service or the router. Write a new provider
class only if we ever need a backend LiteLLM cannot reach.

### 4.3 LSP — substitutability

Every `LLMProvider` implementation must honour the same contract: same return type, same failure
mode (raise `LLMProviderError`, never return `None` or an empty string), same argument meaning.
A provider that silently truncates or returns a dict breaks every caller.

### 4.4 ISP — narrow interfaces

`complete(system_prompt, user_prompt) -> str` is deliberately minimal. Do not widen the Protocol with
streaming, embeddings or tool-calling until a real caller needs them — and when one does, add a
*separate* Protocol (`StreamingLLMProvider`) rather than forcing every provider to implement dead
methods.

### 4.5 DIP — depend on abstractions, inject them

Current code instantiates at import time:

```python
# app/routers/estimations.py  ❌
llm_service = LLMService()          # runs on import, unmockable, one global instance
```

Use FastAPI's dependency injection instead:

```python
# app/dependencies.py  ✅
from functools import lru_cache
from app.config import settings
from app.services.estimation_service import EstimationService
from app.services.llm.factory import get_llm_provider

@lru_cache
def get_estimation_service() -> EstimationService:
    return EstimationService(provider=get_llm_provider(settings))
```

```python
# app/routers/estimations.py  ✅
@router.post("/estimate", response_model=EstimateResponse)
def create_estimate(
    body: EstimateRequest,
    service: Annotated[EstimationService, Depends(get_estimation_service)],
) -> EstimateResponse: ...
```

This buys three things at once: no import-time side effects, `app.dependency_overrides` in tests,
and services that receive their collaborators instead of reaching for globals.

### 4.6 DRY — one source of truth

- Env var names: `config.py` only. Mirror every one in `.env.example`.
- Prompt fragments (rules, output format, examples): defined once in `app/prompts/estimation/<version>/`,
  never duplicated per provider.
- Response shapes: one Pydantic model per payload, reused — do not hand-build dicts.
- Error→status mapping: one place (see §6.3), not repeated `try/except` blocks per endpoint.

DRY is about *knowledge*, not characters. Two snippets that look alike but change for different
reasons should stay separate.

### 4.7 KISS — the smallest thing that holds

- No repository/ORM layer until something is actually persisted.
- No async until there is real I/O concurrency to win; the current sync handlers are correct as-is
  (FastAPI runs `def` handlers in a threadpool).
- No caching layer, message queue, or plugin registry "for later".
- Prefer a plain function over a class with one method; prefer a dict lookup over a class hierarchy.

Apply the abstractions in §4.2 **when the second case appears**, not before. The Protocol above is
justified because the fallback chain in `LLM_MODELS` and a test `FakeProvider` already give two implementations.

---

## 5. Recipes

### 5.1 Add an endpoint

1. Define request/response models in `app/schemas/<domain>.py`.
2. Put the logic in a service method under `app/services/`.
3. Add the handler to the relevant router: validate via the schema, `Depends` the service, map
   domain errors to HTTP.
4. Register the router in `main.py` if it is new. Keep the `/api/v1` prefix.
5. Give the handler an explicit return type and `response_model`.
   Estimation handlers take the request through `Depends(get_safe_request)` so the input guardrails
   run **before any streaming response starts**: a rejection must be an HTTP 400, never an SSE `error`
   event (the SSE handler body only runs after the response has begun).
6. If the UI consumes it: mirror the schema in `web/src/api/types.ts` and add one function to
   `web/src/api/client.ts`. Components call hooks/client, never `fetch` directly.

### 5.2 Add an LLM vendor

1. Add its `<prefix>` → (`ENV_NAME`, key) entry to `key_by_prefix` in `factory.py`.
2. Add its API key to `config.py` **and** `.env.example`.
3. Select it by listing `<prefix>/<model>` in `LLM_MODELS` (order = priority: first is primary, the rest
   are fallbacks).
4. If the vendor needs special request parameters (e.g. prompt caching), handle them in
   `litellm.py`; SDK exceptions must keep translating to `LLMProviderError` there.
5. Do not touch the service, the router, or the schemas.

Only if a backend LiteLLM cannot reach is ever needed: add a class implementing
`StreamingLLMProvider` in a new file and choose it in `factory.py`.

### 5.3 Add / change prompt context (CAG)

- Prompts live in `app/prompts/estimation/<version>/` (`system.j2`, `examples.j2`, `user.j2`).
  Changing wording or examples in a way that alters output → new version folder + bump
  `PROMPT_VERSION`.
- Every estimate endpoint and `/context` accept `?prompt_version=<vN>` (validated against the
  folders on disk in `dependencies.get_prompt_version` → 422); the default is `PROMPT_VERSION`.
  The effective version must flow into rendering, both cache keys and the response, never the constant.
- The active version is `v3` (adds the confidence line, items-then-sum rule, discovery/deployment and
  no-invented-dates rules). The output check (`services/guardrails/output.py`) mirrors the closing-block
  labels of `language.j2`: change them together (a test keeps them in sync).
- `system.j2` = a **static prefix** (rules + examples, never request data) followed by two short
  trailing blocks: `request.j2` (instructions for the chosen detail level / output format) and
  `language.j2` (response language). Keeping every variable part at the end is what lets the
  provider cache the prefix. The description itself only ever goes in `user.j2`.
- Each example declares its parameters (type · detail · format); keep at least one example per
  `output_format` so the few-shots never contradict the requested format.
- Keep examples **consistent with the mandatory output format** in the prompt; if they diverge, fix
  the examples rather than adding compensating instructions.
- Context grows the token bill on *every* request. Before adding an example, ask whether it teaches
  something the existing ones do not (new domain, new granularity, new edge case).
- Prompt assembly is built once at startup, not per request. Keep it that way.

### 5.4 Add a setting

`config.py` → `.env.example` → use it via injected `settings`. Give it a sensible default unless it
is a secret; a missing optional var must not crash boot (see §7).

### 5.5 Update the architecture diagram

Diagrams in `docs/architecture/<name>/` are generated with the [archify](https://github.com/tt-a1i/archify)
agent skill (installed per developer, not a project dependency). Only `candidate.json` (the editable
source) and the rendered `<name>.html` are versioned; archify's `*.finalize*.json`,
`*.browser-check.json` and `*.delivery.json` receipts are git-ignored.

- When a change adds, removes or rewires a node shown in the diagram (router, service, provider,
  prompt pipeline, error mapping), ask the agent to update `candidate.json` from the code and re-run
  archify's `finalize` with `--repo-root .`, then commit both files with the change.
- Every node cites its source files and lines; keep them pointing at real code, never at plans.
- `estimation-flow` is the **overview**: keep it to the main request path (~10 nodes). Plumbing
  (settings, DI, Protocols, error handlers) stays out. When a feature grows its own internals, give
  it a separate diagram in `docs/architecture/<feature>/` and keep a single box for it in the overview.

---

## 6. Conventions

### 6.1 Style

- Type-hint every function signature, including returns (`-> dict[str, str]`, not bare `dict`).
- Modern builtin generics (`list[dict[str, str]]`), no `typing.List`.
- Module-private helpers prefixed with `_`.
- Imports: stdlib / third-party / `app.*`, separated by blank lines.
- Naming: modules and functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE`.

### 6.2 Language

Everything developers read is **English**: identifiers, comments, docstrings, docs (README, this
file), commit messages, logs, CLI/script output, config errors, and the LLM prompts and few-shot
examples (`app/prompts/`, from `v2`; active: `v3`).

**Spanish** is only for what the end user sees: UI copy in `web/src/` and error messages that reach
the UI (e.g. `LLMProviderError` messages, the unexpected-stream error, the API-unreachable message).
Tests may use Spanish sample input and assert on Spanish UI text. The model's *response* language
is chosen per request by the prompt's closing "Response language" block (`language.j2`), not by
the language the instructions are written in. `app/prompts/estimation/v1/` is the original Spanish
prompt, kept only for comparison/rollback. Do not mix languages within a single string.

### 6.3 Errors

- Services raise domain exceptions from `app/exceptions.py`
  (`PromptTemplateError`, `LLMProviderError`, both subclasses of `EstimationError`). Never
  `HTTPException`.
- Current mapping: invalid input is rejected by the Pydantic schema → **422** (FastAPI default);
  `InputRejectedError` (prompt injection, moderation) and `AttachmentError` → **400**;
  `SessionNotFoundError` → **404**;
  `PromptTemplateError` → **500**; upstream LLM failure (`LLMProviderError`) → **502**. On
  `/estimate/stream` the response has already started, so failures arrive as an SSE `error` event.
- Prefer a single `@app.exception_handler` per domain exception in `main.py` over repeating
  `try/except` in every handler.
- Never swallow an exception silently and never leak provider stack traces or API keys in a response
  body.

### 6.4 Docs

Update `README.md` when setup, run commands, or the directory tree change. Update **this file** when
a layer, principle-driven rule, or recipe changes.

---

## 7. Known debt

Fix these opportunistically when you touch the surrounding code; do not replicate them.

| # | Issue | Location | Fix |
|---|---|---|---|
| 2 | All settings required → app crashes on boot with a partial `.env` | `config.py` | Provider keys are now optional (the factory checks the ones in use); defaults for the remaining non-secrets if desired |
| 5 | `estimation` returned as an opaque Markdown blob | `routers/estimations.py` | Consider a structured response (tasks, total hours, weeks) when a consumer needs it — not before |
| 6 | No Python linter/formatter yet | repo-wide | Add `ruff` when style drift shows up (§8) |
| 7 | Semantic cache is unverified against a real Redis Stack, and a setup failure is permanent for the process (no retry; restart to recover) | `services/cache/semantic.py` | Run an integration check against `redis/redis-stack` (index creation, bucket filter, TTL) before moving `SEMANTIC_CACHE_LOG_ONLY` to `false` |

---

## 8. Testing and quality

```bash
pnpm test                # both suites from the repo root (API first, then UI)
pnpm test:api            # uv run pytest  (tests/)
pnpm test:web            # vitest run     (web/src/**/*.test.ts[x])
pnpm test:watch          # vitest in watch mode (UI)
pnpm test:coverage       # pytest --cov=app + vitest --coverage
```

- API: `pytest` + `TestClient`. `tests/conftest.py` pins fake settings and **fails any test that
  reaches the real `litellm.completion`**; use `FakeProvider` / the fake SDK client instead.
- UI: Vitest + React Testing Library + jsdom. Mock `web/src/api/client.ts` at the module boundary;
  query by role/label, not by class names.

CI (`.github/workflows/ci.yml`) runs both suites on every PR to `main`. `main` is protected: changes land
only through a PR whose `api-tests` and `web-tests` checks pass (admins included). Those job names are
required status checks — renaming them blocks every merge until branch protection is updated.
CodeRabbit reviews PRs using `.coderabbit.yaml`, which points reviewers at the rules in this file.
While the repo has fewer than 10 stars CodeRabbit does **not** auto-review: request it on each PR
with `@coderabbitai review` (or `@coderabbitai full review`, or tick **Trigger review** in its status
comment). It is advisory, not a required check, and small open-source repos get about one review
per hour. PRs must also be up to date with `main` before merging.

Pre-commit (Husky + lint-staged, installed by `pnpm install` via `prepare`) runs **the same checks as
CI**: both call `scripts/ci/api.sh` and `scripts/ci/web.sh`, against the staged snapshot only. To
change what is checked, edit those scripts, never the workflow or the hook separately. Don't bypass
the hook with `--no-verify` to land failing code.

Rules:

- Test **services** directly with a fake `LLMProvider` — never hit a real API in a test.
- Redis, moderation and embeddings are always faked (`FakeCache`, fake index/embedder, patched
  `litellm.moderation` / `embedding`, which `conftest.py` blocks); no Redis in tests or CI.
- Test **routers** through `TestClient` with `app.dependency_overrides` swapping the service.
- Every bug fix gets a regression test.
- Never assert on exact LLM output; assert on contract (status code, schema, error mapping).

---

## 9. Definition of done

Before finishing any change:

- [ ] Layer boundaries respected — no HTTP in services, no business logic in routers, no env reads outside `config.py`
- [ ] New behaviour is an *addition* (new file/entry), not a modification of existing working code, where §4.2 applies
- [ ] Collaborators injected, not instantiated at import time
- [ ] Type hints on every new signature; no duplicated knowledge introduced
- [ ] New settings added to `config.py` **and** `.env.example`; no secret committed
- [ ] Errors mapped to the right status codes; nothing swallowed
- [ ] `uv run uvicorn app.main:app --reload` boots and `/health` returns `{"status": "ok"}`
- [ ] If `web/` changed: `pnpm build` and `pnpm lint` pass
- [ ] `README.md` / `AGENTS.md` updated if structure or workflow changed
