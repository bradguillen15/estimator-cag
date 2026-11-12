"""Sessions 7-8 — embedding pipeline.

Turns historical budget JSON into embedding vectors: a structural chunker
(one budget component = one chunk) plus an OpenAI embedder. Since session 8 the
vectors are persisted in Postgres + pgvector (``documents`` / ``chunks``) and
queried by cosine distance.
"""
