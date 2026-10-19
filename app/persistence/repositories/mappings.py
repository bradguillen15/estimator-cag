"""Postgres-backed pseudonym mappings and the ``MappingStore`` built on them.

``lookup_or_create`` must be idempotent under contention: parallel calls with the
same ``(entity_type, original_hash)`` converge to one pseudonym. The UNIQUE
constraint decides the winner: insert with ``ON CONFLICT DO NOTHING`` (Postgres
only), then read the winning row when the insert lost the race.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.persistence.models import PseudonymMappingRow


@dataclass(frozen=True)
class Mapping:
    entity_type: str
    original_hash: str
    pseudonym: str
    created_at: datetime


class SqlMappingsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lookup(self, entity_type: str, original_hash: str) -> Mapping | None:
        row = self._session.execute(
            select(PseudonymMappingRow).where(
                PseudonymMappingRow.entity_type == entity_type,
                PseudonymMappingRow.original_hash == original_hash,
            )
        ).scalar_one_or_none()
        return _to_mapping(row) if row is not None else None

    def lookup_or_create(
        self,
        entity_type: str,
        original_hash: str,
        new_pseudonym_factory: Callable[[], str],
    ) -> Mapping:
        existing = self.lookup(entity_type, original_hash)
        if existing is not None:
            return existing

        stmt = (
            pg_insert(PseudonymMappingRow)
            .values(
                entity_type=entity_type,
                original_hash=original_hash,
                pseudonym=new_pseudonym_factory(),
            )
            .on_conflict_do_nothing(index_elements=["entity_type", "original_hash"])
            .returning(PseudonymMappingRow)
        )
        row = self._session.execute(stmt).scalar_one_or_none()
        self._session.commit()
        if row is not None:
            return _to_mapping(row)

        winner = self.lookup(entity_type, original_hash)
        if winner is None:  # pragma: no cover - the unique constraint guarantees a winner
            raise RuntimeError("pseudonym mapping vanished after a conflicting insert")
        return winner

    def forget(self, entity_type: str, original_hash: str) -> bool:
        """Delete a mapping ("right to be forgotten"). True if a row existed."""
        result = self._session.execute(
            delete(PseudonymMappingRow).where(
                PseudonymMappingRow.entity_type == entity_type,
                PseudonymMappingRow.original_hash == original_hash,
            )
        )
        self._session.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]


class PostgresMappingStore:
    """``MappingStore`` over Postgres: only the HMAC of the original value is stored."""

    def __init__(self, session: Session) -> None:
        self._repo = SqlMappingsRepository(session)

    def lookup_or_create(
        self,
        entity_type: str,
        original_hash: str,
        new_pseudonym_factory: Callable[[], str],
    ) -> str:
        return self._repo.lookup_or_create(
            entity_type, original_hash, new_pseudonym_factory
        ).pseudonym

    def forget(self, entity_type: str, original_hash: str) -> bool:
        return self._repo.forget(entity_type, original_hash)


def _to_mapping(row: PseudonymMappingRow) -> Mapping:
    return Mapping(
        entity_type=row.entity_type,
        original_hash=row.original_hash,
        pseudonym=row.pseudonym,
        created_at=row.created_at,
    )
