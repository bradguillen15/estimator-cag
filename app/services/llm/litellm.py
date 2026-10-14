"""LiteLLM provider: the only module that knows about LiteLLM.

Models are tried in the configured order: the first is the primary, the rest are fallbacks.
The loop is explicit (not LiteLLM's ``fallbacks=``) so every attempt gets the API key of its own
provider and we know which model actually served the answer.
"""

from collections.abc import Callable, Iterator
from itertools import chain
from time import perf_counter
from typing import Any

import litellm
import structlog

from app.exceptions import LLMProviderError
from app.logging_config import estimate_cost_usd
from app.services.llm.base import GenerationMetrics

logger = structlog.get_logger()

# Anthropic only caches when told where: mark the whole system message (the CAG prefix).
_CACHE_SYSTEM_MESSAGE = [{"location": "message", "role": "system"}]


def _to_provider_error(exc: Exception) -> LLMProviderError:
    """Translates LiteLLM failures into a client-safe domain error (raw details stay in the logs)."""
    if isinstance(exc, LLMProviderError):
        return exc
    if isinstance(exc, litellm.RateLimitError):
        return LLMProviderError(
            "El proveedor LLM alcanzó su límite de solicitudes. Inténtalo de nuevo en unos segundos."
        )
    if isinstance(exc, litellm.Timeout):
        return LLMProviderError("El proveedor LLM tardó demasiado en responder.")
    if isinstance(exc, litellm.APIConnectionError):
        return LLMProviderError("No se pudo conectar con el proveedor LLM.")
    if isinstance(exc, (litellm.AuthenticationError, litellm.PermissionDeniedError)):
        return LLMProviderError("El proveedor LLM rechazó las credenciales configuradas.")
    return LLMProviderError("El proveedor LLM devolvió un error al generar la estimación.")


def _close_stream(response: Any) -> None:
    """Best-effort synchronous close of the provider's HTTP stream; never raises.

    LiteLLM's ``CustomStreamWrapper`` only offers ``async aclose()``, which a sync generator cannot
    await, so the underlying ``completion_stream`` is closed directly when it supports it.
    """
    try:
        close = getattr(getattr(response, "completion_stream", None), "close", None)
        if callable(close):
            close()
    except Exception as exc:
        logger.debug("llm_stream_close_failed", error_type=type(exc).__name__)


def _messages(system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _cached_tokens(usage: Any) -> int | None:
    details = getattr(usage, "prompt_tokens_details", None)
    return getattr(details, "cached_tokens", None)


def _cost_usd(model: str, tokens_in: int | None, tokens_out: int | None, cached: int | None) -> float | None:
    """LiteLLM's price table (cache-aware) first; the project's generic estimate as a fallback."""
    if tokens_in is None or tokens_out is None:
        return None
    try:
        input_cost, output_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=tokens_in,
            completion_tokens=tokens_out,
            cache_read_input_tokens=cached or 0,
        )
        return round(input_cost + output_cost, 6)
    except Exception:
        return estimate_cost_usd(model.split("/", 1)[-1], tokens_in, tokens_out)


class LiteLLMProvider:
    name = "litellm"

    def __init__(
        self,
        models: list[str],
        api_keys: dict[str, str],
        timeout: float = 30,
        retries: int = 2,
        max_tokens: int = 16000,
        completion: Callable[..., Any] | None = None,
    ) -> None:
        if not models:
            raise ValueError("LiteLLMProvider needs at least one model.")
        self.model = models[0]
        self._models = list(models)
        self._api_keys = dict(api_keys)
        self._timeout = timeout
        self._retries = retries
        self._max_tokens = max_tokens
        self._completion = completion

    def _call(self, model: str, messages: list[dict[str, str]], **extra: Any) -> Any:
        prefix = model.split("/", 1)[0]
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "api_key": self._api_keys.get(prefix),
            "timeout": self._timeout,
            "num_retries": self._retries,
            "max_tokens": self._max_tokens,
            **extra,
        }
        if prefix == "anthropic":
            params["cache_control_injection_points"] = _CACHE_SYSTEM_MESSAGE
        completion = self._completion or litellm.completion
        return completion(**params)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return self.complete_messages(_messages(system_prompt, user_prompt))

    def complete_messages(self, messages: list[dict[str, str]]) -> str:
        """Same fallback chain as ``complete``, for a full conversation (system message first)."""
        call_logger = logger.bind(model=self.model, provider=self.name, stream=False, messages=len(messages))
        call_logger.info("llm_call_started")
        started_at = perf_counter()
        last_error: Exception | None = None

        for attempt, model in enumerate(self._models):
            try:
                completion = self._call(model, messages)
                content = completion.choices[0].message.content
                if not content:
                    raise LLMProviderError("El proveedor LLM devolvió una respuesta vacía.")
            except Exception as exc:
                last_error = exc
                call_logger.warning("llm_model_failed", failed_model=model, error_type=type(exc).__name__)
                continue

            usage = completion.usage
            tokens_in = usage.prompt_tokens if usage else None
            tokens_out = usage.completion_tokens if usage else None
            cached = _cached_tokens(usage)
            call_logger.info(
                "llm_call_completed",
                served_model=model,
                latency_ms=round((perf_counter() - started_at) * 1000, 1),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cached_tokens=cached,
                cost_usd=_cost_usd(model, tokens_in, tokens_out, cached),
                finish_reason=completion.choices[0].finish_reason,
                cache_hit=bool(cached),
                fallback_used=attempt > 0,
            )
            return content

        return self._fail(call_logger, last_error, started_at)

    def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        metrics: GenerationMetrics | None = None,
    ) -> Iterator[str]:
        call_logger = logger.bind(model=self.model, provider=self.name, stream=True)
        call_logger.info("llm_call_started")
        started_at = perf_counter()
        last_error: Exception | None = None
        chunks: Iterator[Any] | None = None
        raw_stream: Any = None
        served_model = self.model
        attempts = 0

        # Fallback only applies until the first text chunk: after that the client already has text.
        for attempts, served_model in enumerate(self._models, start=1):
            try:
                raw_stream, chunks = self._open_stream(served_model, system_prompt, user_prompt)
                break
            except Exception as exc:
                last_error = exc
                call_logger.warning(
                    "llm_model_failed", failed_model=served_model, error_type=type(exc).__name__
                )
        if chunks is None:
            self._fail(call_logger, last_error, started_at)
            return

        tokens_in: int | None = None
        tokens_out: int | None = None
        cached: int | None = None
        finish_reason: str | None = None
        if metrics is not None:
            metrics.model = served_model

        try:
            for chunk in chunks:
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    tokens_in = usage.prompt_tokens
                    tokens_out = usage.completion_tokens
                    cached = _cached_tokens(usage)
                    if metrics is not None:
                        metrics.input_tokens = tokens_in
                        metrics.output_tokens = tokens_out
                        metrics.cached_tokens = cached

                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta.content
                if delta:
                    yield delta
        except Exception as exc:
            self._fail(call_logger, exc, started_at)
            return
        finally:
            # Runs on completion, mid-stream errors and GeneratorExit (client disconnected).
            _close_stream(raw_stream)

        latency_ms = round((perf_counter() - started_at) * 1000, 1)
        cost = _cost_usd(served_model, tokens_in, tokens_out, cached)
        if metrics is not None:
            metrics.latency_seconds = latency_ms / 1000
            metrics.cost_usd = cost
        call_logger.info(
            "llm_call_completed",
            served_model=served_model,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cached_tokens=cached,
            cost_usd=cost,
            finish_reason=finish_reason,
            cache_hit=bool(cached),
            fallback_used=attempts > 1,
        )

    def _open_stream(
        self, model: str, system_prompt: str, user_prompt: str
    ) -> tuple[Any, Iterator[Any]]:
        """Opens the stream and reads until the first text chunk, so failures here can fall back.

        Returns the raw provider stream (for closing) and the chunk iterator. On failure the raw
        stream is closed here, so an abandoned attempt never leaks its connection.
        """
        raw = self._call(
            model,
            _messages(system_prompt, user_prompt),
            stream=True,
            stream_options={"include_usage": True},
        )
        try:
            response = iter(raw)
            head: list[Any] = []
            for chunk in response:
                head.append(chunk)
                if chunk.choices and chunk.choices[0].delta.content:
                    return raw, chain(head, response)
            raise LLMProviderError("El proveedor LLM devolvió una respuesta vacía.")
        except BaseException:
            _close_stream(raw)
            raise

    def _fail(self, call_logger: Any, exc: Exception | None, started_at: float) -> Any:
        """Logs the terminal failure and raises the safe domain error."""
        error = exc or LLMProviderError("El proveedor LLM devolvió un error al generar la estimación.")
        call_logger.error(
            "llm_call_failed",
            error_type=type(error).__name__,
            error_msg=str(error),
            latency_ms=round((perf_counter() - started_at) * 1000, 1),
        )
        raise _to_provider_error(error) from error
