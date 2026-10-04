"""LiteLLMProvider: ``litellm.completion`` is replaced by a fake callable (injected, never the real one)."""

from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

import litellm
import pytest

from app.config import Settings
from app.exceptions import LLMProviderError
from app.services.llm.base import GenerationMetrics
from app.services.llm.factory import get_llm_provider
from app.services.llm.litellm import LiteLLMProvider

_SECRET = "sk-SECRET123 raw provider detail"
_MODELS = ["anthropic/claude-sonnet-5-5", "openai/gpt-test"]
_KEYS = {"anthropic": "key-a", "openai": "key-o"}


class FakeCompletion:
    """Scripted ``litellm.completion``: one behaviour per call, in order; records every call."""

    def __init__(self, *behaviours: Callable[[], Any] | Exception | Any) -> None:
        self._behaviours = list(behaviours)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        behaviour = self._behaviours.pop(0)
        if isinstance(behaviour, Exception):
            raise behaviour
        return behaviour() if callable(behaviour) else behaviour


def _provider(fake: FakeCompletion, models: list[str] | None = None) -> LiteLLMProvider:
    return LiteLLMProvider(models=models or _MODELS, api_keys=_KEYS, completion=fake, timeout=7, retries=3, max_tokens=99)


def _response(content: str | None, *, cached: int | None = 0) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
        usage=SimpleNamespace(
            prompt_tokens=120,
            completion_tokens=30,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
        ),
    )


def _chunk(content: str | None = None, *, finish: str | None = None, usage: tuple[int, int, int] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[] if content is None and finish is None else [SimpleNamespace(delta=SimpleNamespace(content=content), finish_reason=finish)],
        usage=SimpleNamespace(
            prompt_tokens=usage[0],
            completion_tokens=usage[1],
            prompt_tokens_details=SimpleNamespace(cached_tokens=usage[2]),
        )
        if usage
        else None,
    )


def _timeout() -> Exception:
    return litellm.Timeout(_SECRET, model="m", llm_provider="anthropic")


LITELLM_ERRORS: list[tuple[Exception, str]] = [
    (litellm.RateLimitError(_SECRET, llm_provider="p", model="m"), "límite de solicitudes"),
    (litellm.Timeout(_SECRET, model="m", llm_provider="p"), "tardó demasiado"),
    (litellm.APIConnectionError(_SECRET, llm_provider="p", model="m"), "No se pudo conectar"),
    (litellm.AuthenticationError(_SECRET, llm_provider="p", model="m"), "credenciales"),
    (litellm.InternalServerError(_SECRET, llm_provider="p", model="m"), "devolvió un error"),
]


# --- complete() -------------------------------------------------------------------------------


def test_complete_returns_the_text_from_the_primary_model() -> None:
    fake = FakeCompletion(_response("## Estimación: Demo"))

    assert _provider(fake).complete("SYSTEM", "USER") == "## Estimación: Demo"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == "anthropic/claude-sonnet-5-5"
    assert call["messages"] == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "USER"},
    ]
    assert (call["api_key"], call["timeout"], call["num_retries"], call["max_tokens"]) == ("key-a", 7, 3, 99)


def test_requests_never_carry_sampling_params() -> None:
    fake = FakeCompletion(_response("ok"), _response("ok"))
    provider = _provider(fake)
    provider.complete("S", "U")
    fake2 = FakeCompletion(iter([_chunk("ok")]))
    list(_provider(fake2).stream("S", "U"))

    for call in fake.calls + fake2.calls:
        assert "temperature" not in call and "top_p" not in call


def test_anthropic_calls_mark_the_system_message_for_caching_but_openai_calls_do_not() -> None:
    fake = FakeCompletion(_timeout(), _response("ok"))
    _provider(fake).complete("S", "U")

    anthropic_call, openai_call = fake.calls
    assert anthropic_call["cache_control_injection_points"] == [{"location": "message", "role": "system"}]
    assert "cache_control_injection_points" not in openai_call
    assert openai_call["api_key"] == "key-o"


def test_complete_messages_sends_the_whole_conversation_with_fallback() -> None:
    messages = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "U2"},
    ]
    fake = FakeCompletion(_timeout(), _response("A2"))

    assert _provider(fake).complete_messages(messages) == "A2"
    assert [call["messages"] for call in fake.calls] == [messages, messages]
    assert fake.calls[0]["cache_control_injection_points"] == [{"location": "message", "role": "system"}]


def test_complete_falls_back_when_the_primary_fails() -> None:
    fake = FakeCompletion(_timeout(), _response("respuesta de respaldo"))

    assert _provider(fake).complete("S", "U") == "respuesta de respaldo"
    assert [c["model"] for c in fake.calls] == _MODELS


def test_complete_raises_a_safe_error_when_every_model_fails() -> None:
    primary = litellm.RateLimitError(_SECRET, llm_provider="anthropic", model="m")
    last = litellm.AuthenticationError(_SECRET, llm_provider="openai", model="m")
    fake = FakeCompletion(primary, last)

    with pytest.raises(LLMProviderError, match="credenciales") as caught:
        _provider(fake).complete("S", "U")

    assert "SECRET" not in str(caught.value) and "key-" not in str(caught.value)
    assert caught.value.__cause__ is last


@pytest.mark.parametrize(("sdk_error", "expected"), LITELLM_ERRORS)
def test_complete_translates_litellm_errors(sdk_error: Exception, expected: str) -> None:
    with pytest.raises(LLMProviderError, match=expected) as caught:
        _provider(FakeCompletion(sdk_error), models=["anthropic/claude-sonnet-5-5"]).complete("S", "U")
    assert "SECRET" not in str(caught.value)


@pytest.mark.parametrize("content", ["", None])
def test_complete_rejects_an_empty_answer(content: str | None) -> None:
    with pytest.raises(LLMProviderError, match="vacía"):
        _provider(FakeCompletion(_response(content)), models=["anthropic/claude-sonnet-5-5"]).complete("S", "U")


def test_complete_turns_a_malformed_response_into_a_domain_error() -> None:
    broken = SimpleNamespace(choices=[], usage=None)
    with pytest.raises(LLMProviderError):
        _provider(FakeCompletion(broken), models=["anthropic/claude-sonnet-5-5"]).complete("S", "U")


def test_complete_tolerates_missing_usage() -> None:
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="texto"), finish_reason="stop")], usage=None)
    assert _provider(FakeCompletion(response)).complete("S", "U") == "texto"


# --- stream() ---------------------------------------------------------------------------------


def test_stream_yields_only_text_deltas_and_fills_metrics() -> None:
    chunks = [_chunk(""), _chunk("## Esti"), _chunk("mación"), _chunk(None), _chunk(" final", finish="stop"), _chunk(usage=(200, 45, 150))]
    fake = FakeCompletion(iter(chunks))
    metrics = GenerationMetrics(model="placeholder")

    assert list(_provider(fake).stream("S", "U", metrics=metrics)) == ["## Esti", "mación", " final"]
    assert fake.calls[0]["stream"] is True
    assert fake.calls[0]["stream_options"] == {"include_usage": True}
    assert (metrics.model, metrics.input_tokens, metrics.output_tokens, metrics.cached_tokens) == (
        "anthropic/claude-sonnet-5-5",
        200,
        45,
        150,
    )
    assert metrics.latency_seconds is not None and metrics.latency_seconds >= 0
    assert metrics.cost_usd is not None and metrics.cost_usd > 0


def test_stream_works_without_a_metrics_object() -> None:
    assert list(_provider(FakeCompletion(iter([_chunk("hola")]))).stream("S", "U")) == ["hola"]


def test_stream_falls_back_when_opening_the_stream_fails() -> None:
    fake = FakeCompletion(_timeout(), iter([_chunk("respaldo"), _chunk(usage=(10, 2, 0))]))
    metrics = GenerationMetrics(model="placeholder")

    assert list(_provider(fake).stream("S", "U", metrics=metrics)) == ["respaldo"]
    assert [c["model"] for c in fake.calls] == _MODELS
    assert metrics.model == "openai/gpt-test"


def test_stream_falls_back_when_the_first_chunk_fails() -> None:
    def _dies_immediately() -> Iterator[SimpleNamespace]:
        raise _timeout()
        yield  # pragma: no cover

    fake = FakeCompletion(_dies_immediately, iter([_chunk("respaldo")]))

    assert list(_provider(fake).stream("S", "U")) == ["respaldo"]


def test_stream_does_not_fall_back_after_text_was_sent() -> None:
    def _broken() -> Iterator[SimpleNamespace]:
        yield _chunk("parcial")
        raise _timeout()

    fake = FakeCompletion(_broken, iter([_chunk("nunca")]))
    received: list[str] = []

    with pytest.raises(LLMProviderError, match="tardó demasiado") as caught:
        for token in _provider(fake).stream("S", "U"):
            received.append(token)

    assert received == ["parcial"]
    assert len(fake.calls) == 1
    assert "SECRET" not in str(caught.value)


def test_stream_raises_when_every_model_fails() -> None:
    fake = FakeCompletion(_timeout(), litellm.AuthenticationError(_SECRET, llm_provider="openai", model="m"))
    with pytest.raises(LLMProviderError, match="credenciales"):
        list(_provider(fake).stream("S", "U"))


def test_stream_with_no_text_is_an_empty_answer_error() -> None:
    fake = FakeCompletion(iter([_chunk(usage=(1, 0, 0))]))
    with pytest.raises(LLMProviderError, match="vacía"):
        list(_provider(fake, models=["anthropic/claude-sonnet-5-5"]).stream("S", "U"))


class FakeStream:
    """Iterable like LiteLLM's ``CustomStreamWrapper``: the HTTP stream is ``completion_stream``."""

    def __init__(self, items: list[Any] | None = None, error: Exception | None = None) -> None:
        self._items = list(items or [])
        self._error = error
        self.closed = 0
        self.completion_stream = SimpleNamespace(close=self._close)

    def _close(self) -> None:
        self.closed += 1

    def __iter__(self) -> Iterator[Any]:
        yield from self._items
        if self._error is not None:
            raise self._error


def test_stream_closes_the_provider_stream_on_normal_completion() -> None:
    stream = FakeStream([_chunk("hola"), _chunk(usage=(1, 1, 0))])
    assert list(_provider(FakeCompletion(stream)).stream("S", "U")) == ["hola"]
    assert stream.closed == 1


def test_stream_closes_the_provider_stream_when_the_consumer_stops_early() -> None:
    stream = FakeStream([_chunk("uno"), _chunk("dos"), _chunk("tres")])
    generator = _provider(FakeCompletion(stream)).stream("S", "U")
    assert next(generator) == "uno"
    assert stream.closed == 0
    generator.close()  # what happens when the client disconnects
    assert stream.closed == 1


def test_stream_closes_the_provider_stream_on_a_mid_stream_error() -> None:
    stream = FakeStream([_chunk("parcial")], error=_timeout())
    with pytest.raises(LLMProviderError):
        list(_provider(FakeCompletion(stream)).stream("S", "U"))
    assert stream.closed == 1


def test_stream_closes_the_provider_stream_on_an_empty_response() -> None:
    stream = FakeStream([_chunk(usage=(1, 0, 0))])
    with pytest.raises(LLMProviderError, match="vacía"):
        list(_provider(FakeCompletion(stream), models=["anthropic/claude-sonnet-5-5"]).stream("S", "U"))
    assert stream.closed == 1


def test_stream_closes_the_abandoned_stream_before_falling_back() -> None:
    abandoned = FakeStream(error=_timeout())
    fallback = FakeStream([_chunk("respaldo")])
    assert list(_provider(FakeCompletion(abandoned, fallback)).stream("S", "U")) == ["respaldo"]
    assert (abandoned.closed, fallback.closed) == (1, 1)


def test_a_failing_close_never_breaks_the_stream() -> None:
    stream = FakeStream([_chunk("hola")])
    stream.completion_stream = SimpleNamespace(close=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert list(_provider(FakeCompletion(stream)).stream("S", "U")) == ["hola"]


# --- factory ----------------------------------------------------------------------------------


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "openai_api_key": "k-o",
        "anthropic_api_key": "k-a",
        "llm_models": _MODELS,
        "app_env": "development",
        "log_level": "INFO",
    }
    return Settings(**{**values, **overrides})


def test_factory_builds_the_litellm_provider_with_the_ordered_models() -> None:
    provider = get_llm_provider(_settings())
    assert isinstance(provider, LiteLLMProvider)
    assert (provider.name, provider.model) == ("litellm", "anthropic/claude-sonnet-5-5")


@pytest.mark.parametrize("missing", ["anthropic_api_key", "openai_api_key"])
def test_factory_fails_at_build_time_when_a_configured_provider_has_no_key(missing: str) -> None:
    with pytest.raises(ValueError, match="API_KEY is required"):
        get_llm_provider(_settings(**{missing: None}))


def test_factory_only_needs_keys_for_the_configured_models() -> None:
    provider = get_llm_provider(_settings(llm_models=["anthropic/claude-sonnet-5-5"], openai_api_key=None))
    assert isinstance(provider, LiteLLMProvider)


def test_factory_rejects_unsupported_model_entries() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM_MODELS entry"):
        get_llm_provider(_settings(llm_models=["gemini/flash"]))


def test_llm_models_can_be_a_comma_separated_string() -> None:
    assert _settings(llm_models=" anthropic/a , openai/b ").llm_models == ["anthropic/a", "openai/b"]


def test_the_real_litellm_completion_is_blocked_in_tests() -> None:
    with pytest.raises(AssertionError, match="real LLM"):
        litellm.completion(model="openai/x", messages=[])
