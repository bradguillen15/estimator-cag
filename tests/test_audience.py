"""Audience tier: resolver precedence, prompt block, cache isolation and the route contract."""

import pytest
from fastapi.testclient import TestClient

from app.prompts.loader import render_estimation_prompt
from app.schemas.estimations import Audience, EstimationRequest
from app.schemas.sessions import ProjectMetadata
from app.services.audience import resolve_audience
from app.services.cache.base import make_cache_key
from app.services.cache.semantic import make_bucket
from app.services.estimation_service import PROMPT_VERSION, EstimationService
from app.services.sessions import SessionStore
from tests.conftest import VALID_REQUEST, FakeCache, FakeProvider

GOOD_TEXT = "## Estimación: Demo\n\n**Total estimado: 40 horas**\n**Confianza: alta — claro**"
MODELS = ("anthropic/a",)


def _request(**overrides: object) -> EstimationRequest:
    return EstimationRequest.model_validate({**VALID_REQUEST, **overrides})


# --- resolver ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "tier", "rule"),
    [
        ("We signed an NDA and the project is confidential.", Audience.EXECUTIVE, "compliance_terms"),
        ("El cliente exige cumplir GDPR y el RGPD.", Audience.EXECUTIVE, "compliance_terms"),
        ("This is for the board and our investors.", Audience.EXECUTIVE, "compliance_terms"),
        ("Hay un acuerdo de confidencialidad firmado.", Audience.EXECUTIVE, "compliance_terms"),
        ("We present it at the board meeting next week.", Audience.EXECUTIVE, "compliance_terms"),
        ("Add a Kanban board with drag and drop.", Audience.DEFAULT, "default"),
        ("A dashboard board view for the team.", Audience.DEFAULT, "default"),
        ("The CEO wants the ROI before approving it.", Audience.EXECUTIVE, "executive_terms"),
        ("Necesitamos un resumen ejecutivo para el patrocinador.", Audience.EXECUTIVE, "executive_terms"),
        ("A REST API over a database with CI/CD on Kubernetes.", Audience.DEVELOPER, "technical_audience"),
        ("Microservicios con una base de datos y endpoints nuevos.", Audience.DEVELOPER, "technical_audience"),
        ("Plan the next sprint and update the roadmap.", Audience.PM, "pm_signals"),
        ("Los stakeholders piden hitos y un backlog priorizado.", Audience.PM, "pm_signals"),
        ("Portal interno para reservar salas con calendario.", Audience.DEFAULT, "default"),
    ],
)
def test_each_rule_fires_in_english_and_spanish(text: str, tier: Audience, rule: str) -> None:
    result = resolve_audience(text)

    assert (result.audience, result.rule) == (tier, rule)


def test_one_developer_keyword_is_not_enough_and_repeats_do_not_count() -> None:
    assert resolve_audience("We run on docker.").rule == "default"
    assert resolve_audience("docker, Docker and DOCKER again").rule == "default"


def test_explicit_value_beats_every_other_rule() -> None:
    nda = "Under NDA, with a REST API and a database; the sprint starts soon."

    result = resolve_audience(nda, explicit=Audience.PM)

    assert (result.audience, result.rule) == (Audience.PM, "explicit_override")
    assert resolve_audience(nda, explicit=Audience.DEFAULT).audience is Audience.DEFAULT


def test_precedence_compliance_then_executive_then_developer_then_pm() -> None:
    api_db = "a REST API and a database"
    assert resolve_audience(f"{api_db}, NDA, CEO").rule == "compliance_terms"
    assert resolve_audience(f"{api_db}, the CEO asks").rule == "executive_terms"
    assert resolve_audience(f"{api_db} and the next sprint").rule == "technical_audience"
    assert resolve_audience("the next sprint").rule == "pm_signals"


def test_small_team_metadata_means_developer_but_not_over_pm_free_text_rules() -> None:
    small = ProjectMetadata(assumed_team_size=2)

    assert resolve_audience("Portal interno sencillo", metadata=small).rule == "small_team"
    assert resolve_audience("Portal interno sencillo", metadata=ProjectMetadata(assumed_team_size=3)).rule == "default"
    # Text rules rank above the metadata rule.
    assert resolve_audience("Under NDA", metadata=small).rule == "compliance_terms"
    # ...and the metadata rule ranks above PM vocabulary.
    assert resolve_audience("next sprint", metadata=small).rule == "small_team"


def test_an_nda_remembered_in_the_agreed_scope_counts() -> None:
    metadata = ProjectMetadata(agreed_scope="Work is covered by an NDA.")

    assert resolve_audience("Add a calendar view", metadata=metadata).rule == "compliance_terms"


# --- prompt -----------------------------------------------------------------------------------


def test_default_and_unset_audience_render_the_same_prompt_without_a_block() -> None:
    plain, _ = render_estimation_prompt(_request())
    default, _ = render_estimation_prompt(_request(audience="default"))

    assert default == plain
    assert "## Audience" not in plain


@pytest.mark.parametrize(
    ("tier", "phrase"),
    [("executive", "business outcomes"), ("pm", "milestones"), ("developer", "technical breakdown")],
)
def test_a_tier_adds_one_trailing_block_after_the_static_prefix(tier: str, phrase: str) -> None:
    plain, _ = render_estimation_prompt(_request())

    system, _ = render_estimation_prompt(_request(audience=tier))

    assert system.startswith(plain)
    tail = system[len(plain) :]
    assert tail.count("## Audience") == 1 and f"`{tier}`" in tail and phrase in tail


def test_the_block_also_renders_on_session_turns_and_keeps_the_default_identical() -> None:
    metadata = ProjectMetadata(project_name="Portal")
    plain, _ = render_estimation_prompt(_request(), project_metadata=metadata)

    with_tier, _ = render_estimation_prompt(_request(audience="pm"), project_metadata=metadata)

    assert "## Audience" in with_tier and "## Audience" not in plain
    assert render_estimation_prompt(_request(audience="default"), project_metadata=metadata)[0] == plain


# --- cache ------------------------------------------------------------------------------------


def test_the_default_tier_keeps_the_existing_keys_and_a_tier_changes_them() -> None:
    base = make_cache_key(_request(), "v3", MODELS)

    assert make_cache_key(_request(audience="default"), "v3", MODELS) == base
    keys = {make_cache_key(_request(audience=t), "v3", MODELS) for t in ("executive", "pm", "developer")}
    assert len(keys | {base}) == 4
    buckets = {make_bucket(_request(audience=t), "v3") for t in ("executive", "pm", "developer")}
    assert len(buckets | {make_bucket(_request(), "v3")}) == 4
    assert make_bucket(_request(audience="default"), "v3") == make_bucket(_request(), "v3")


def test_two_tiers_never_share_a_cached_answer(fake_cache: FakeCache) -> None:
    provider = FakeProvider(text=GOOD_TEXT)
    service = EstimationService(provider, cache=fake_cache, cache_models=MODELS)

    service.generate(_request(audience="executive"))
    service.generate(_request(audience="developer"))
    service.generate(_request(audience="executive"))

    assert len(provider.calls) == 2  # the third call is a hit on the executive entry
    assert "`executive`" in provider.calls[0][0] and "`developer`" in provider.calls[1][0]


def test_an_inferred_tier_is_part_of_the_key_too(fake_cache: FakeCache) -> None:
    service = EstimationService(FakeProvider(text=GOOD_TEXT), cache=fake_cache, cache_models=MODELS)
    request = _request(description="Portal under an NDA to reserve rooms with a calendar.")

    service.generate(request)

    expected = make_cache_key(request.model_copy(update={"audience": Audience.EXECUTIVE}), PROMPT_VERSION, MODELS)
    assert fake_cache.sets == [expected]


# --- routes -----------------------------------------------------------------------------------


def test_estimate_reports_the_inferred_tier_and_rule(client: TestClient) -> None:
    body = {**VALID_REQUEST, "description": "Portal under an NDA to reserve rooms with a calendar."}

    data = client.post("/api/v1/estimate", json=body).json()

    assert (data["audience"], data["audience_rule"]) == ("executive", "compliance_terms")


def test_estimate_accepts_an_explicit_audience(client: TestClient, fake_provider: FakeProvider) -> None:
    response = client.post("/api/v1/estimate", json={**VALID_REQUEST, "audience": "developer"})

    data = response.json()
    assert response.status_code == 200
    assert (data["audience"], data["audience_rule"]) == ("developer", "explicit_override")
    assert "## Audience" in fake_provider.calls[0][0]


def test_estimate_without_signals_reports_default(client: TestClient) -> None:
    data = client.post("/api/v1/estimate", json=VALID_REQUEST).json()

    assert (data["audience"], data["audience_rule"]) == ("default", "default")


@pytest.mark.parametrize("path", ["/api/v1/estimate", "/api/v1/estimate/stream", "/api/v1/estimate/reviewed"])
def test_an_invalid_audience_is_a_422(client: TestClient, path: str) -> None:
    assert client.post(path, json={**VALID_REQUEST, "audience": "intern"}).status_code == 422


def test_session_turn_accepts_the_form_field_and_the_detail_exposes_it(
    client: TestClient, session_store: SessionStore, fake_provider: FakeProvider
) -> None:
    session = session_store.create()
    form = {
        "transcript": VALID_REQUEST["description"],
        "project_type": VALID_REQUEST["project_type"],
        "detail_level": VALID_REQUEST["detail_level"],
        "output_format": VALID_REQUEST["output_format"],
    }
    url = f"/api/v1/sessions/{session.session_id}/estimate"
    assert client.get(f"/api/v1/sessions/{session.session_id}").json()["last_audience"] is None

    response = client.post(url, data={**form, "audience": "pm"})

    assert response.status_code == 200
    assert (response.json()["audience"], response.json()["audience_rule"]) == ("pm", "explicit_override")
    assert "## Audience" in fake_provider.message_calls[-1][0]["content"]
    detail = client.get(f"/api/v1/sessions/{session.session_id}").json()
    assert (detail["last_audience"], detail["last_audience_rule"]) == ("pm", "explicit_override")
    assert client.post(url, data={**form, "audience": "intern"}).status_code == 422


def test_session_turn_uses_the_session_metadata_for_the_small_team_rule(
    client: TestClient, session_store: SessionStore
) -> None:
    session = session_store.create()
    session.metadata = ProjectMetadata(assumed_team_size=1)
    form = {
        "transcript": VALID_REQUEST["description"],
        "project_type": VALID_REQUEST["project_type"],
        "detail_level": VALID_REQUEST["detail_level"],
        "output_format": VALID_REQUEST["output_format"],
    }

    data = client.post(f"/api/v1/sessions/{session.session_id}/estimate", data=form).json()

    assert (data["audience"], data["audience_rule"]) == ("developer", "small_team")
