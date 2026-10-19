"""The mapping store — persistent backing for consistent pseudonymization.

Implementation here:

* :class:`InMemoryMappingStore` — for tests and one-off scripts.

A Postgres-backed store (keyed by the HMAC of the original value, never the
plaintext) belongs in ``app/persistence`` and just has to satisfy the
:class:`MappingStore` Protocol. Deleting a row by hash kills reversibility
without ever having stored the plaintext ("right to be forgotten").

Stores are *idempotent*: looking up the same ``(entity_type, hash)``
twice returns the same pseudonym, regardless of the order of calls. Concurrent
callers converge thanks to the unique constraint upstream.
"""
from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable


@runtime_checkable
class MappingStore(Protocol):
    def lookup_or_create(
        self,
        entity_type: str,
        original_hash: str,
        new_pseudonym_factory: Callable[[], str],
    ) -> str:  # pragma: no cover - protocol stub
        ...

    def forget(self, entity_type: str, original_hash: str) -> bool: ...


class InMemoryMappingStore:
    """Simple dict-backed mapping store for tests and scripts."""

    def __init__(self) -> None:
        self._mappings: dict[tuple[str, str], str] = {}

    def lookup_or_create(
        self,
        entity_type: str,
        original_hash: str,
        new_pseudonym_factory: Callable[[], str],
    ) -> str:
        key = (entity_type, original_hash)
        if key not in self._mappings:
            self._mappings[key] = new_pseudonym_factory()
        return self._mappings[key]

    def forget(self, entity_type: str, original_hash: str) -> bool:
        return self._mappings.pop((entity_type, original_hash), None) is not None
