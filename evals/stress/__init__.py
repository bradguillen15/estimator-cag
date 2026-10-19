"""Stress test scaffolding for the CAG (Cache-Augmented Generation) session pipeline.

Instruments the conversational estimator under load and produces a CSV (plus a
hand-written ``REPORT.md``) that quantifies where the context-augmented approach
degrades: latency, cost per turn, recall drift across many turns and growing
attachments.

- ``scenarios``  -- synthetic multi-turn conversations with fact trackers.
- ``metrics``    -- ``LatencyBudgetMetric``, ``CostBudgetMetric``, ``MemoryDriftMetric``.
- ``run``        -- CLI runner: scenarios x attachment sizes x repeats -> ``results.csv``.
- ``fixtures``   -- deterministic PDF generator (the PDFs themselves are git-ignored).

Dev tool only: it may import ``app.*``; ``app/`` never imports ``evals``.
"""
