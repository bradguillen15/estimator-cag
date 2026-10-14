from collections.abc import AsyncIterator
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from starlette.concurrency import iterate_in_threadpool

from app.dependencies import get_estimation_service, get_prompt_version, get_safe_request
from app.exceptions import EstimationError
from app.schemas.review import ReviewedEstimateResponse
from app.schemas.estimations import (
    EstimationRequest,
    EstimationResponse,
    PromptContextResponse,
)
from app.services.estimation_service import EstimationService
from app.services.llm.base import GenerationMetrics

logger = structlog.get_logger()

router = APIRouter(tags=["estimations"])

Service = Annotated[EstimationService, Depends(get_estimation_service)]
# The request after the input guardrails (a rejection is an HTTP 400 before any handler runs).
SafeRequest = Annotated[EstimationRequest, Depends(get_safe_request)]

PromptVersion = Annotated[str, Depends(get_prompt_version)]

_UNEXPECTED_STREAM_ERROR = "Error inesperado al generar la estimación."


@router.get("/context", response_model=PromptContextResponse)
def get_prompt_context(service: Service, prompt_version: PromptVersion) -> PromptContextResponse:
    return PromptContextResponse(
        prompt_version=prompt_version,
        examples_markdown=service.context_examples(prompt_version),
    )


# Domain errors are mapped to HTTP status codes by the exception handlers in main.py.
@router.post("/estimate", response_model=EstimationResponse)
def create_estimate(body: SafeRequest, service: Service, prompt_version: PromptVersion) -> EstimationResponse:
    metrics = GenerationMetrics(model=service.model)
    text = service.generate(body, prompt_version, metrics=metrics)
    audience = service.resolve_audience(body)
    return EstimationResponse(
        text=text,
        prompt_version=prompt_version,
        cache_hit=metrics.cache_hit,
        audience=audience.audience,
        audience_rule=audience.rule,
    )


@router.post("/estimate/reviewed", response_model=ReviewedEstimateResponse)
def create_reviewed_estimate(body: SafeRequest, service: Service, prompt_version: PromptVersion) -> ReviewedEstimateResponse:
    """Critic review loop: up to 2 x REVIEW_MAX_ITERATIONS LLM calls, caches bypassed."""
    result = service.generate_with_critic(body, prompt_version)
    audience = service.resolve_audience(body)
    return ReviewedEstimateResponse(
        estimation=result.estimate,
        prompt_version=prompt_version,
        audience=audience.audience,
        audience_rule=audience.rule,
        final_verdict=result.final_verdict,
        iterations=result.iterations,
    )


@router.post("/estimate/stream", response_class=EventSourceResponse)
async def create_estimate_stream(
    body: SafeRequest,
    request: Request,
    service: Service,
    prompt_version: PromptVersion,
) -> AsyncIterator[ServerSentEvent]:
    metrics = GenerationMetrics(model=service.model)
    audience = service.resolve_audience(body)

    # The HTTP status is already 200 once streaming starts, so failures travel as an `error` event.
    stream = None
    try:
        stream = service.generate_stream(body, metrics=metrics, prompt_version=prompt_version)
        async for token in iterate_in_threadpool(stream):
            if await request.is_disconnected():
                break
            yield ServerSentEvent(data=token, event="token")
        else:
            yield ServerSentEvent(
                data={
                    "model": metrics.model,
                    "provider": service.provider_name,
                    "input_tokens": metrics.input_tokens,
                    "output_tokens": metrics.output_tokens,
                    "latency_seconds": metrics.latency_seconds,
                    "cache_hit": metrics.cache_hit,
                    "prompt_version": prompt_version,
                    "audience": audience.audience.value,
                    "audience_rule": audience.rule,
                },
                event="done",
            )
    except EstimationError as exc:
        yield ServerSentEvent(data={"detail": str(exc)}, event="error")
    except Exception:
        logger.exception("estimate_stream_failed")
        yield ServerSentEvent(data={"detail": _UNEXPECTED_STREAM_ERROR}, event="error")
    finally:
        # iterate_in_threadpool does not close the sync generator on early exit (disconnect).
        if stream is not None:
            stream.close()
