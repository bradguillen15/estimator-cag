"""Per-turn observation: the ``turn_observed`` event, ``observation`` in the response and the session detail."""

import dataclasses
import logging
from collections.abc import Iterator

import pytest
import structlog
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from app.schemas.estimations import EstimationRequest
from app.schemas.sessions import TurnObservation
from app.services import estimation_service
from app.services.estimation_service import EstimationService, SessionTurn
from app.services.sessions import ConversationHistory, Session, SessionStore
from tests.conftest import VALID_REQUEST, FakeProvider

OBSERVATION_KEYS = set(TurnObservation.model_fields)
FORM = {
    "transcript": VALID_REQUEST["description"],
    "project_type": VALID_REQUEST["project_type"],
    "detail_level": VALID_REQUEST["detail_level"],
    "output_format": VALID_REQUEST["output_format"],
}


@pytest.fixture
def info_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The suite pins LOG_LEVEL=WARNING, which filters ``info`` events before ``capture_logs`` sees them."""
    previous = structlog.get_config()
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.INFO), cache_logger_on_first_use=False)
    monkeypatch.setattr(estimation_service, "logger", structlog.get_logger())
    yield
    structlog.configure(**previous)


def _session(max_turns: int = 2) -> Session:
    return SessionStore(max_turns=max_turns).create()


def _turn(service: EstimationService, text: str = VALID_REQUEST["description"]) -> SessionTurn:
    return service.prepare_session_turn(EstimationRequest.model_validate({**VALID_REQUEST, "description": text}), [])


def test_the_observation_has_the_thirteen_fields() -> None:
    assert len(OBSERVATION_KEYS) == 13


def test_a_turn_emits_one_turn_observed_event_with_every_field(info_logging: None) -> None:
    service = EstimationService(FakeProvider())
    session = _session()

    with capture_logs() as logs:
        service.generate_for_session(_turn(service), session)

    events = [log for log in logs if log["event"] == "turn_observed"]
    assert len(events) == 1
    assert OBSERVATION_KEYS <= set(events[0])
    assert events[0]["session_id"] == session.session_id
    assert events[0]["cache_hit_kind"] == "none"
    assert session.last_observation is not None


def test_turn_index_is_not_capped_by_the_window_and_totals_include_every_call() -> None:
    service = EstimationService(FakeProvider())
    session = _session(max_turns=2)
    observations: list[TurnObservation] = []

    for n in range(4):
        service.generate_for_session(_turn(service, f"Turn {n}: {VALID_REQUEST['description']}"), session)
        assert session.last_observation is not None
        observations.append(session.last_observation)

    assert [o.turn_index for o in observations] == [1, 2, 3, 4]
    assert [o.messages_in_window for o in observations] == [2, 4, 4, 4]
    # FakeProvider reports 100 in / 20 out / $0.01 per call: actor + extractor, plus the summarizer once turns overflow.
    assert [(o.tokens_in, o.tokens_out, o.cost_usd) for o in observations[:2]] == [(200, 40, 0.02)] * 2
    assert [(o.tokens_in, o.tokens_out, o.cost_usd) for o in observations[2:]] == [(300, 60, 0.03)] * 2
    assert observations[3].summary_chars > 0
    assert observations[3].latency_ms >= 0


def test_attachment_chars_are_reported_apart_from_the_enriched_transcript() -> None:
    service = EstimationService(FakeProvider())
    session = _session()
    turn = dataclasses.replace(_turn(service), attachments_chars=42)

    service.generate_for_session(turn, session)

    assert session.last_observation is not None
    assert session.last_observation.attachments_total_chars == 42
    assert session.last_observation.enriched_transcript_chars == len(turn.request.description)


def test_the_response_carries_the_observation_and_the_detail_exposes_memory(
    client: TestClient, session_store: SessionStore, fake_provider: FakeProvider
) -> None:
    session = session_store.create()
    session.history = ConversationHistory(max_turns=1)
    url = f"/api/v1/sessions/{session.session_id}/estimate"
    anchor = f"We signed the contract and the NDA applies. {VALID_REQUEST['description']}"

    client.post(url, data={**FORM, "transcript": anchor})
    body = client.post(url, data=FORM).json()

    assert set(body["observation"]) == OBSERVATION_KEYS
    assert body["observation"]["turn_index"] == 2
    assert body["observation"]["session_id"] == session.session_id

    detail = client.get(f"/api/v1/sessions/{session.session_id}").json()
    assert detail["last_observation"] == body["observation"]
    assert detail["anchors"] == [session.history.anchors[0].user]
    assert "signed the contract" in detail["anchors"][0]
    assert detail["summary"] == session.history.summary
    assert body["observation"]["anchors_count"] == len(detail["anchors"]) == 1


def test_a_new_session_has_no_observation(client: TestClient, session_store: SessionStore) -> None:
    detail = client.get(f"/api/v1/sessions/{session_store.create().session_id}").json()

    assert detail["last_observation"] is None
    assert detail["anchors"] == []
    assert detail["summary"] == ""
