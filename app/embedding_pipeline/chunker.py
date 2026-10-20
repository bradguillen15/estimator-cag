"""Structural chunker for budget JSON.

Strategy: trust the document structure. One :class:`BudgetComponent` becomes
exactly one :class:`Chunk`. No overlap, no fixed-size splitting of long
descriptions — if a description is abnormally large, that is a data point we
want to surface (via ``token_count``) and discuss, not paper over.

The parent budget context is prepended to every chunk (a *contextual chunk
header*): without it a component like "Authentication backend" would lose track
of which client and sector it belongs to.
"""

from __future__ import annotations

from functools import cache

import tiktoken

from app.embedding_pipeline.schemas import Budget, BudgetComponent, Chunk

# The embedding model whose tokenizer we count against.
EMBEDDING_MODEL = "text-embedding-3-small"


@cache
def _encoding() -> tiktoken.Encoding:
    """Resolve the tokenizer once, on first use: loading it may download the BPE file, which must not
    happen while importing app.main (an offline container would fail to boot)."""
    return tiktoken.encoding_for_model(EMBEDDING_MODEL)


class JSONStructuralChunker:
    """Turns budgets into one chunk per component."""

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for budget in budgets:
            for component in budget.components:
                chunks.append(self._chunk_component(budget, component))
        return chunks

    def _chunk_component(self, budget: Budget, component: BudgetComponent) -> Chunk:
        text = self._render_text(budget, component)
        return Chunk(
            chunk_id=f"{budget.budget_id}::{component.component_id}",
            text=text,
            metadata={
                "budget_id": budget.budget_id,
                "component_id": component.component_id,
                "client_sector": budget.client_metadata.sector,
                "main_technology": budget.main_technology,
                "year": budget.year,
                "complexity": component.complexity,
                "estimated_hours": component.estimated_hours,
            },
            # disallowed_special=(): a field containing e.g. '<|endoftext|>' is counted as plain text, not rejected.
            token_count=len(_encoding().encode(text, disallowed_special=())),
        )

    @staticmethod
    def _render_text(budget: Budget, component: BudgetComponent) -> str:
        """Parent context header + component detail. This is what gets embedded."""
        return (
            f"[Project: {budget.project_summary}]\n"
            f"[Client sector: {budget.client_metadata.sector} | "
            f"Year: {budget.year} | Main tech: {budget.main_technology}]\n"
            f"\n"
            f"Component: {component.name}\n"
            f"Description: {component.description}\n"
            f"Tech stack: {', '.join(component.tech_stack)}\n"
            f"Complexity: {component.complexity}\n"
            f"Estimated hours: {component.estimated_hours}"
        )
