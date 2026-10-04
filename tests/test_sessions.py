"""Session state (sliding-window history, project metadata, in-process store) and POST /sessions."""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.exceptions import SessionNotFoundError
from app.schemas.sessions import ProjectMetadata
from app.services.sessions import DEFAULT_MAX_TURNS, ConversationHistory, SessionStore, TurnRecord

# --- ConversationHistory ----------------------------------------------------------------------


def test_history_keeps_turns_in_chronological_order() -> None:
    history = ConversationHistory(max_turns=3)
    history.add_turn("u1", "a1")
    history.add_turn("u2", "a2")

    assert history.messages == [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
    ]
    assert len(history) == 2


def test_history_drops_the_oldest_whole_turns_beyond_the_window() -> None:
    history = ConversationHistory(max_turns=2)
    for n in range(1, 5):
        history.add_turn(f"u{n}", f"a{n}")

    assert len(history) == 2
    assert [m["content"] for m in history.messages] == ["u3", "a3", "u4", "a4"]
    assert history.messages[0]["role"] == "user"


def test_history_messages_is_a_copy() -> None:
    history = ConversationHistory()
    history.add_turn("u1", "a1")

    history.messages[0]["content"] = "tampered"
    history.messages.clear()

    assert history.messages[0]["content"] == "u1"


def test_default_window_is_six_turns() -> None:
    assert DEFAULT_MAX_TURNS == 6
    assert ConversationHistory().max_turns == 6


def test_to_messages_list_starts_with_the_given_system_prompt() -> None:
    history = ConversationHistory(max_turns=2)
    assert history.to_messages_list("S0") == [{"role": "system", "content": "S0"}]

    for n in range(1, 4):
        history.add_turn(f"u{n}", f"a{n}")

    assert history.to_messages_list("S1") == [
        {"role": "system", "content": "S1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
    ]


def test_history_rejects_an_empty_window() -> None:
    with pytest.raises(ValueError):
        ConversationHistory(max_turns=0)


# --- ProjectMetadata --------------------------------------------------------------------------


def test_metadata_starts_empty() -> None:
    metadata = ProjectMetadata()

    assert metadata.project_name is None
    assert metadata.assumed_team_size is None
    assert metadata.mentioned_technologies == []
    assert metadata.agreed_scope is None


def test_metadata_rejects_a_non_positive_team_size() -> None:
    with pytest.raises(ValidationError):
        ProjectMetadata(assumed_team_size=0)


# --- SessionStore -----------------------------------------------------------------------------


def test_store_creates_independent_sessions_and_gets_them_back() -> None:
    store = SessionStore(max_turns=4)
    first = store.create()
    second = store.create()

    first.history.add_turn("u1", "a1")
    first.metadata.project_name = "Portal"

    assert first.session_id != second.session_id
    assert store.get(first.session_id) is first
    assert len(store.get(second.session_id).history) == 0
    assert store.get(second.session_id).metadata.project_name is None
    assert first.history.max_turns == 4


def test_store_raises_a_domain_error_for_an_unknown_session() -> None:
    with pytest.raises(SessionNotFoundError):
        SessionStore().get("missing")


# --- POST /sessions ---------------------------------------------------------------------------


def test_create_session_returns_201_with_a_uuid4(client: TestClient, session_store: SessionStore) -> None:
    response = client.post("/api/v1/sessions")

    assert response.status_code == 201
    session_id = response.json()["session_id"]
    assert uuid.UUID(session_id).version == 4
    assert _store_has(session_store, session_id)


def test_each_call_creates_a_distinct_session(client: TestClient, session_store: SessionStore) -> None:
    first = client.post("/api/v1/sessions").json()["session_id"]
    second = client.post("/api/v1/sessions").json()["session_id"]

    assert first != second
    assert _store_has(session_store, first) and _store_has(session_store, second)


def _store_has(store: SessionStore, session_id: str) -> bool:
    try:
        store.get(session_id)
    except SessionNotFoundError:
        return False
    return True


# --- Session.record_turn / SessionStore.list --------------------------------------------------


_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


def test_record_turn_adds_to_history_and_bumps_updated_at() -> None:
    session = SessionStore().create()
    # A fixed past timestamp: two datetime.now() calls can tie, which made this flaky.
    session.updated_at = _EPOCH

    session.record_turn("u1", "a1")

    assert len(session.history) == 1
    assert session.updated_at > _EPOCH


def test_store_list_only_returns_sessions_with_turns_most_recent_first() -> None:
    store = SessionStore()
    empty = store.create()
    older = store.create()
    newer = store.create()
    older.record_turn("u", "a")
    newer.record_turn("u", "a")
    # Explicit timestamps: consecutive datetime.now() calls can tie and make the order random.
    older.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    newer.updated_at = datetime(2026, 1, 2, tzinfo=UTC)

    assert [s.session_id for s in store.list()] == [newer.session_id, older.session_id]
    assert empty.session_id not in [s.session_id for s in store.list()]

    older.record_turn("u2", "a2")  # bumps to now, later than both fixed dates
    assert [s.session_id for s in store.list()] == [older.session_id, newer.session_id]


# --- GET /sessions ----------------------------------------------------------------------------


def test_list_sessions_returns_summaries_of_sessions_with_turns(
    client: TestClient, session_store: SessionStore
) -> None:
    session_store.create()  # no turns: not listed
    session = session_store.create()
    session.metadata.project_name = "Portal"
    session.record_turn("u1", "a1")

    response = client.get("/api/v1/sessions")

    assert response.status_code == 200
    [row] = response.json()
    assert row["session_id"] == session.session_id
    assert row["project_name"] == "Portal"
    assert row["history_turns"] == 1
    assert row["created_at"] and row["updated_at"]


def test_list_sessions_is_empty_without_turns(client: TestClient, session_store: SessionStore) -> None:
    session_store.create()

    assert client.get("/api/v1/sessions").json() == []


# --- GET /sessions/{id} -----------------------------------------------------------------------


def _record(n: int, attachments: tuple[str, ...] = ()) -> TurnRecord:
    return TurnRecord(
        description=f"typed {n}",
        attachment_names=attachments,
        estimate=f"a{n}",
        prompt_version="v3",
        created_at=datetime(2026, 1, 1, 10, n, tzinfo=UTC),
    )


def test_record_turn_trims_display_turns_with_the_history_window() -> None:
    session = SessionStore(max_turns=2).create()

    for n in range(1, 4):
        session.record_turn(f"u{n}", f"a{n}", _record(n))

    assert [t.description for t in session.turns] == ["typed 2", "typed 3"]
    assert len(session.history) == 2


def test_get_session_returns_metadata_and_turns_in_order(
    client: TestClient, session_store: SessionStore
) -> None:
    session = session_store.create()
    session.metadata.project_name = "Portal"
    session.record_turn("u1", "a1", _record(1, ("spec.pdf",)))
    session.record_turn("u2", "a2", _record(2))

    response = client.get(f"/api/v1/sessions/{session.session_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session.session_id
    assert body["project_metadata"]["project_name"] == "Portal"
    assert body["history_turns"] == 2
    assert "last_estimate" not in body
    assert [t["description"] for t in body["turns"]] == ["typed 1", "typed 2"]
    assert [t["estimate"] for t in body["turns"]] == ["a1", "a2"]
    assert body["turns"][0]["attachment_names"] == ["spec.pdf"]
    assert body["turns"][1]["attachment_names"] == []
    assert body["turns"][0]["prompt_version"] == "v3"
    assert body["turns"][0]["cache_hit"] is False


def test_get_session_without_turns_has_no_turns(client: TestClient, session_store: SessionStore) -> None:
    session = session_store.create()

    body = client.get(f"/api/v1/sessions/{session.session_id}").json()

    assert body["turns"] == []
    assert body["history_turns"] == 0


def test_get_unknown_session_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/sessions/missing").status_code == 404
