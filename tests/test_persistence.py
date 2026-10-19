import importlib

from sqlalchemy import Engine

import app.persistence.database as database
from app.persistence.models import Base
from app.persistence.repositories.mappings import PostgresMappingStore
from app.services.ingestion.pii.mapping_store import MappingStore


def test_importing_persistence_builds_no_engine() -> None:
    module = importlib.reload(database)
    assert not [v for v in vars(module).values() if isinstance(v, Engine)]


def test_build_engine_is_lazy() -> None:
    # Port 1 refuses connections: building the engine must not try to connect.
    engine = database.build_engine("postgresql+psycopg://u:p@localhost:1/db")
    assert engine.url.database == "db"
    assert database.build_session_factory(engine) is not None


def test_models_declare_expected_tables() -> None:
    assert set(Base.metadata.tables) == {"pseudonym_mappings", "ingestion_jobs"}
    mappings = Base.metadata.tables["pseudonym_mappings"]
    assert {c.name for c in mappings.columns} == {
        "id", "entity_type", "original_hash", "pseudonym", "created_at",
    }


def test_postgres_store_satisfies_mapping_store_protocol() -> None:
    assert isinstance(PostgresMappingStore(session=None), MappingStore)  # type: ignore[arg-type]
