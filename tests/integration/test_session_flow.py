"""End-to-end session flows over HTTP with ``httpx.AsyncClient`` (ASGI transport, no server).

The whole app runs for real (routing, multipart parsing, extraction, guardrails, prompts, history
and metadata); only the LLM is a fake that answers from what it is sent. These tests prove that
information *reaches* the model and *flows* across turns, not how well a real model uses it.
"""

import json
import re
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest

from app.dependencies import get_estimation_service, get_session_store
from app.main import app
from app.services.estimation_service import EstimationService
from app.services.sessions import SessionStore
from tests.conftest import VALID_REQUEST
from tests.test_attachments import _pdf

MAX_TURNS = 3
FORM = {
    "transcript": VALID_REQUEST["description"],
    "project_type": VALID_REQUEST["project_type"],
    "detail_level": VALID_REQUEST["detail_level"],
    "output_format": VALID_REQUEST["output_format"],
}


class ContentAwareProvider:
    """A fake LLM that answers from the prompt it receives.

    - Estimate calls: 80 hours if the latest user message mentions SSO, 40 otherwise.
    - Metadata extraction calls (recognised by their system prompt): JSON with the project name
      "Reservas" and, from the second turn on, a team of 3.
    """

    name = "content-aware"
    model = "content-aware-model"

    def __init__(self) -> None:
        self.estimate_calls: list[list[dict[str, str]]] = []
        self.extractions = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if system_prompt.startswith("You extract the facts"):
            self.extractions += 1
            facts: dict[str, object] = {"project_name": "Reservas", "mentioned_technologies": ["React"]}
            if self.extractions > 1:
                facts["assumed_team_size"] = 3
            return json.dumps(facts)
        return self.complete_messages(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        )

    def complete_messages(self, messages: list[dict[str, str]]) -> str:
        self.estimate_calls.append(messages)
        hours = 80 if "SSO" in messages[-1]["content"] else 40
        return f"## Estimación: Reservas\n\n**Total estimado: {hours} horas**"

    def stream(self, *args: object, **kwargs: object) -> Iterator[str]:
        raise NotImplementedError


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def provider() -> ContentAwareProvider:
    return ContentAwareProvider()


@pytest.fixture
async def http(provider: ContentAwareProvider) -> AsyncIterator[httpx.AsyncClient]:
    store = SessionStore(max_turns=MAX_TURNS)
    app.dependency_overrides[get_estimation_service] = lambda: EstimationService(provider)  # type: ignore[arg-type]
    app.dependency_overrides[get_session_store] = lambda: store
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _new_session(http: httpx.AsyncClient) -> str:
    response = await http.post("/api/v1/sessions")
    assert response.status_code == 201
    return response.json()["session_id"]


async def _estimate(http: httpx.AsyncClient, session_id: str, **kwargs: object) -> dict[str, object]:
    response = await http.post(f"/api/v1/sessions/{session_id}/estimate", **kwargs)  # type: ignore[arg-type]
    assert response.status_code == 200, response.text
    return response.json()


def _total_hours(text: object) -> int:
    match = re.search(r"Total estimado: (\d+) horas", str(text))
    assert match, text
    return int(match.group(1))


@pytest.mark.anyio
async def test_two_linked_requests_update_the_project_metadata(http: httpx.AsyncClient) -> None:
    session_id = await _new_session(http)

    first = await _estimate(http, session_id, data=FORM)
    second = await _estimate(http, session_id, data={**FORM, "transcript": "Añade notificaciones push al portal."})

    assert first["project_metadata"] == {
        "project_name": "Reservas",
        "assumed_team_size": None,
        "mentioned_technologies": ["React"],
        "agreed_scope": None,
    }
    assert second["project_metadata"]["assumed_team_size"] == 3  # type: ignore[index]
    assert second["project_metadata"]["project_name"] == "Reservas"  # type: ignore[index]  # kept
    assert (first["history_turns"], second["history_turns"]) == (1, 2)


@pytest.mark.anyio
async def test_an_attached_pdf_changes_the_estimate(http: httpx.AsyncClient) -> None:
    pdf = ("attachments", ("spec.pdf", _pdf("Login with SSO through Azure AD"), "application/pdf"))

    without = await _estimate(http, await _new_session(http), data=FORM)
    with_pdf = await _estimate(http, await _new_session(http), data=FORM, files=[pdf])

    assert _total_hours(without["text"]) == 40
    assert _total_hours(with_pdf["text"]) == 80


@pytest.mark.anyio
async def test_eight_turns_never_send_more_than_max_turns_of_history(
    http: httpx.AsyncClient, provider: ContentAwareProvider
) -> None:
    session_id = await _new_session(http)

    for turn in range(8):
        body = await _estimate(http, session_id, data={**FORM, "transcript": f"Turno {turn}. {FORM['transcript']}"})
        assert body["history_turns"] == min(turn + 1, MAX_TURNS)

    assert len(provider.estimate_calls) == 8
    for messages in provider.estimate_calls:
        assert messages[0]["role"] == "system"  # the invariant: always first, never trimmed
        replayed = messages[1:-1]
        assert len(replayed) <= 2 * MAX_TURNS
    last = provider.estimate_calls[-1]
    assert [m["role"] for m in last[1:-1]] == ["user", "assistant"] * MAX_TURNS
    assert "Turno 4." in last[1]["content"]  # turns 0-3 already left the window
