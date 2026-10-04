"""Session turns replay the history window: messages sent to the LLM and what the history keeps."""

from fastapi.testclient import TestClient

from app.services.sessions import ConversationHistory, Session, SessionStore
from tests.conftest import VALID_REQUEST, FakeProvider
from tests.test_attachments import _pdf

FORM = {
    "transcript": VALID_REQUEST["description"],
    "project_type": VALID_REQUEST["project_type"],
    "detail_level": VALID_REQUEST["detail_level"],
    "output_format": VALID_REQUEST["output_format"],
}


def _post(client: TestClient, session: Session, **kwargs: object) -> None:
    response = client.post(f"/api/v1/sessions/{session.session_id}/estimate", **kwargs)  # type: ignore[arg-type]
    assert response.status_code == 200


def test_the_second_turn_replays_the_first(
    client: TestClient, session_store: SessionStore, fake_provider: FakeProvider
) -> None:
    session = session_store.create()

    _post(client, session, data=FORM)
    _post(client, session, data={**FORM, "transcript": "Ahora añade una app móvil para reservar desde el teléfono."})

    first, second = fake_provider.message_calls
    assert [m["role"] for m in first] == ["system", "user"]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "user"]
    assert second[1] == first[1]  # the first user turn, replayed as it was
    assert second[2]["content"] == fake_provider.text
    assert "app móvil" in second[3]["content"]
    assert len(session.history) == 2


def test_the_system_prompt_is_rebuilt_with_the_current_metadata(
    client: TestClient, session_store: SessionStore, fake_provider: FakeProvider
) -> None:
    session = session_store.create()
    _post(client, session, data=FORM)
    session.metadata.project_name = "Reservas"  # as if the extractor had found it

    _post(client, session, data=FORM)

    assert "Reservas" not in fake_provider.message_calls[0][0]["content"]
    assert "- Project name: Reservas" in fake_provider.message_calls[1][0]["content"]


def test_old_turns_leave_the_window(client: TestClient, session_store: SessionStore, fake_provider: FakeProvider) -> None:
    session = session_store.create()
    session.history = ConversationHistory(max_turns=2)

    for n in range(4):
        _post(client, session, data={**FORM, "transcript": f"Turno número {n}: {FORM['transcript']}"})

    last = fake_provider.message_calls[-1]
    assert len(last) == 1 + 2 * 2 + 1  # system + 2 kept turns + the new message
    assert "Turno número 1" in last[1]["content"]
    assert all("Turno número 0" not in m["content"] for m in last)


def test_history_keeps_a_reference_to_attachments_not_their_text(
    client: TestClient, session_store: SessionStore, fake_provider: FakeProvider
) -> None:
    session = session_store.create()
    pdf = ("attachments", ("spec.pdf", _pdf("Login with SSO"), "application/pdf"))

    _post(client, session, data=FORM, files=[pdf])
    _post(client, session, data=FORM)

    assert "Login with SSO" in fake_provider.message_calls[0][-1]["content"]  # the LLM saw it once
    replayed = fake_provider.message_calls[1][1]["content"]
    assert "[attachments: spec.pdf]" in replayed
    assert "Login with SSO" not in replayed


def test_history_never_stores_raw_pii(client: TestClient, session_store: SessionStore) -> None:
    session = session_store.create()
    transcript = f"{FORM['transcript']} Contacto: ana@example.com"
    pdf = ("attachments", ("spec.pdf", _pdf("Login with SSO"), "application/pdf"))

    _post(client, session, data={**FORM, "transcript": transcript}, files=[pdf])

    assert "ana@example.com" not in session.history.messages[0]["content"]


def test_display_turns_store_what_was_typed_and_attachment_names_not_their_text(
    client: TestClient, session_store: SessionStore, fake_provider: FakeProvider
) -> None:
    session = session_store.create()
    pdf = ("attachments", ("spec.pdf", _pdf("Login with SSO"), "application/pdf"))

    _post(client, session, data=FORM, files=[pdf])
    _post(client, session, data=FORM)

    first, second = session.turns
    assert first.description == FORM["transcript"]
    assert first.attachment_names == ("spec.pdf",)
    assert first.estimate == fake_provider.text
    assert first.prompt_version
    assert "Login with SSO" not in first.description
    assert second.attachment_names == ()
    body = client.get(f"/api/v1/sessions/{session.session_id}").json()
    assert [t["attachment_names"] for t in body["turns"]] == [["spec.pdf"], []]
