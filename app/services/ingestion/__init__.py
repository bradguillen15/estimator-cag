"""Ingestion subsystem (framework-free: no FastAPI, no env reads).

* ``catalog`` — versioned audit of data sources (what we ingest and why).
* ``loaders`` + ``parsers`` — raw bytes → list[Document] (the canonical contract).
* ``documents`` — the ``Document`` model every parser produces.
"""
