#!/usr/bin/env python3
"""Ingestion pre-flight: catches the usual setup pitfalls before a demo or a run.

Prints OK/FAIL per check; exit code is non-zero if any check fails. Reads config only
through ``app.config.settings``.

    uv run python scripts/ingestion/preflight.py      # or: pnpm preflight
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

OK = "✅"
FAIL = "❌"
API_URL = "http://127.0.0.1:8000"
SPACY_HINT = "uv run python -m spacy download es_core_news_md"

# import name per distribution (fpdf2 -> fpdf, pyyaml -> yaml)
_PACKAGES = (
    "pandas",
    "pandera",
    "yaml",
    "sqlalchemy",
    "psycopg",
    "alembic",
    "presidio_analyzer",
    "presidio_anonymizer",
    "spacy",
    "faker",
    "fpdf",
)


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


def check_python_version() -> str:
    if sys.version_info < (3, 13):
        raise RuntimeError(f"Python >=3.13 required, found {sys.version.split()[0]}")
    return sys.version.split()[0]


def check_packages() -> str:
    missing = []
    for name in _PACKAGES:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    if missing:
        raise RuntimeError(f"cannot import: {', '.join(missing)} (run `uv sync`)")
    return f"{len(_PACKAGES)} packages import"


def check_spacy_model() -> str:
    import spacy

    model = settings.presidio_spacy_model
    try:
        nlp = spacy.load(model)
    except OSError as exc:
        raise RuntimeError(f"model {model!r} not installed; run `{SPACY_HINT}`") from exc
    persons = [e.text for e in nlp("Laura Fernández firmó el contrato.").ents if e.label_ == "PER"]
    if not persons:
        raise RuntimeError(f"{model!r} loaded but detected no PER entity")
    return f"{model} loaded; PER: {persons}"


def check_seed_data() -> str:
    root = _path(settings.ingestion_data_root)
    if not root.is_dir():
        raise RuntimeError(f"{root} not found")
    files = [p for p in root.rglob("*") if p.is_file()]
    if not files:
        raise RuntimeError(f"{root} has no files")
    return f"{len(files)} files under {root}"


def check_catalog() -> str:
    from app.services.ingestion.catalog.loader import load_catalog

    catalog = load_catalog(_path(settings.catalog_path))
    return f"version {catalog.version}, {len(catalog.included_sources())} included sources"


def check_api_health() -> str:
    import httpx

    try:
        response = httpx.get(f"{API_URL}/health", timeout=2.0)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"{API_URL}/health unreachable ({type(exc).__name__}); is `pnpm dev` running?") from exc
    if response.status_code != 200:
        raise RuntimeError(f"/health returned {response.status_code}")
    return "200 OK"


def check_postgres() -> str:
    from sqlalchemy import inspect

    from app.persistence.database import build_engine

    engine = build_engine(settings.database_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    expected = {"pseudonym_mappings", "ingestion_jobs", "alembic_version"}
    missing = expected - tables
    if missing:
        raise RuntimeError(f"missing tables {sorted(missing)}; run `uv run alembic upgrade head`")
    return f"tables present: {sorted(expected)}"


CHECKS: list[tuple[str, Callable[[], str]]] = [
    ("Python version", check_python_version),
    ("Required packages", check_packages),
    ("spaCy model", check_spacy_model),
    ("Seed data", check_seed_data),
    ("Catalog validates", check_catalog),
    ("API /health", check_api_health),
    ("Postgres + migration", check_postgres),
]


def _short(exc: Exception) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    return f"{type(exc).__name__}: {text}"[:240]


def main() -> int:
    print("Ingestion pre-flight\n")
    failed = 0
    for name, fn in CHECKS:
        try:
            detail = fn()
        except Exception as exc:  # noqa: BLE001 - report every failure, never traceback
            failed += 1
            print(f"{FAIL}  {name}: {_short(exc)}")
        else:
            print(f"{OK}  {name}: {detail}")
    print()
    if failed:
        print(f"{FAIL}  {failed} check(s) failed")
        return 1
    print(f"{OK}  All checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
