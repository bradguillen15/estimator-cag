"""Estimation use case.

Pipeline (input guardrails run earlier, in ``prepare``): exact cache -> semantic cache -> LLM ->
output check -> store. Only answers that completed and passed the output check are cached.

Session turns (``prepare_session_turn`` + ``generate_for_session``) skip both caches: their
prompt also carries the session's history and project metadata, which the cache key does not
cover, so a hit could replay an answer built on another conversation. After the answer, the turn
is added to the history window and the metadata is updated for the next turn.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from time import perf_counter

import structlog

from app.prompts.loader import PROMPT_VERSION, render_estimation_examples, render_estimation_prompt
from app.schemas.estimations import EstimationRequest
from app.services.cache.base import CachedAnswer, NoOpCache, ResponseCache, make_cache_key
from app.services.cache.semantic import NoOpSemanticCache, SemanticCache, SemanticLookup
from app.services.attachments import Attachment, build_description, display_name
from app.services.guardrails.input import InputGuardrails, redact_pii
from app.services.guardrails.output import check_estimation_output
from app.services.llm.base import EstimationLLMProvider, GenerationMetrics
from app.services.metadata_extractor import MetadataExtractor
from app.services.sessions import Session

__all__ = ["PROMPT_VERSION", "EstimationService", "SessionTurn"]

logger = structlog.get_logger()


@dataclass(frozen=True)
class SessionTurn:
    """A prepared session request.

    ``request.description`` is what the LLM sees this turn (transcript + attachment text, after the
    guardrails). ``history_description`` is what the history keeps: the transcript plus a reference
    to the attachments, not their text, so the replayed window stays cheap. Facts taken from the
    attachments survive through ``project_metadata``.
    """

    request: EstimationRequest
    history_description: str


class EstimationService:
    def __init__(
        self,
        provider: EstimationLLMProvider,
        guardrails: InputGuardrails | None = None,
        cache: ResponseCache | None = None,
        cache_models: Sequence[str] | None = None,
        semantic_cache: SemanticCache | None = None,
        metadata_extractor: MetadataExtractor | None = None,
    ) -> None:
        self._provider = provider
        self._metadata_extractor = metadata_extractor or MetadataExtractor(provider)
        self._guardrails = guardrails or InputGuardrails()
        self._cache = cache if cache is not None else NoOpCache()
        self._semantic = semantic_cache if semantic_cache is not None else NoOpSemanticCache()
        # Part of the cache key: changing the configured model list must not serve old answers.
        self._cache_models = tuple(cache_models) if cache_models else (provider.model,)

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def model(self) -> str:
        return self._provider.model

    def context_examples(self, prompt_version: str = PROMPT_VERSION) -> str:
        """CAG examples the model receives in the system prompt (Markdown)."""
        return render_estimation_examples(prompt_version)

    def prepare(self, request: EstimationRequest) -> EstimationRequest:
        """Runs the input guardrails; returns the request with the sanitized description.

        Raises ``InputRejectedError``. Call it before ``generate``/``generate_stream``, which expect
        an already prepared request.
        """
        safe_description = self._guardrails.check(request.description)
        return request.model_copy(update={"description": safe_description})

    def prepare_session_turn(self, request: EstimationRequest, attachments: Sequence[Attachment]) -> SessionTurn:
        """Appends the attachment text to the transcript and runs the guardrails on the whole of it.

        Raises ``AttachmentError`` or ``InputRejectedError``. An instruction hidden in an attachment
        is rejected like one in the transcript.
        """
        description = build_description(request.description, attachments)
        safe_description = self._guardrails.check(description)
        history_description = safe_description
        if attachments:
            # The transcript was already checked as part of the whole; only redact it again.
            names = ", ".join(display_name(attachment.filename) for attachment in attachments)
            history_description = f"{redact_pii(request.description)[0]}\n\n[attachments: {names}]"
        return SessionTurn(
            request=request.model_copy(update={"description": safe_description}),
            history_description=history_description,
        )

    def generate(
        self,
        request: EstimationRequest,
        prompt_version: str = PROMPT_VERSION,
        metrics: GenerationMetrics | None = None,
    ) -> str:
        """Returns the estimate; ``metrics.cache_hit`` is set when it came from a cache."""
        key = make_cache_key(request, prompt_version, self._cache_models)
        cached = self._cache.get(key)
        if cached is not None:
            if metrics is not None:
                metrics.cache_hit = True
            return cached.text

        semantic = self._semantic.lookup(request, prompt_version)
        if semantic.answer is not None:
            if metrics is not None:
                metrics.cache_hit = True
            return semantic.answer.text

        system, user = render_estimation_prompt(request, prompt_version)
        text = self._provider.complete(system, user)
        if self._passes_output_check(request, text, prompt_version):
            self._store(key, semantic, CachedAnswer(text=text))
        return text

    def generate_for_session(
        self,
        turn: SessionTurn,
        session: Session,
        prompt_version: str = PROMPT_VERSION,
    ) -> str:
        """One session turn: the history window + the new message, then update history and metadata.

        The system prompt is rebuilt every turn from the current ``project_metadata``. No caching
        (see the module docstring). A failed metadata extraction keeps the old facts.
        """
        request = turn.request
        system, user = render_estimation_prompt(request, prompt_version, project_metadata=session.metadata)
        messages = [*session.history.to_messages_list(system), {"role": "user", "content": user}]
        text = self._provider.complete_messages(messages)
        self._passes_output_check(request, text, prompt_version)  # logged only: nothing to cache

        _, history_user = render_estimation_prompt(
            request.model_copy(update={"description": turn.history_description}), prompt_version
        )
        session.record_turn(history_user, text)
        session.metadata = self._metadata_extractor.update(
            session.metadata, request.description, text, request.language.value
        )
        return text

    def generate_stream(
        self,
        request: EstimationRequest,
        metrics: GenerationMetrics | None = None,
        prompt_version: str = PROMPT_VERSION,
    ) -> Iterator[str]:
        started_at = perf_counter()
        key = make_cache_key(request, prompt_version, self._cache_models)
        cached = self._cache.get(key)
        semantic = SemanticLookup(bucket="")
        if cached is None:
            semantic = self._semantic.lookup(request, prompt_version)
            cached = semantic.answer
        if cached is not None:
            if metrics is not None:
                metrics.cache_hit = True
                metrics.model = cached.model or "cache"
                metrics.latency_seconds = round(perf_counter() - started_at, 4)
            # Replay line by line so the client sees the same token events as a live generation.
            yield from cached.text.splitlines(keepends=True)
            return

        system, user = render_estimation_prompt(request, prompt_version)
        chunks: list[str] = []
        for chunk in self._provider.stream(system, user, metrics=metrics):
            chunks.append(chunk)
            yield chunk
        # Reached only when the stream completed (an error or a client disconnect skips it), so a
        # broken stream is never checked nor cached.
        text = "".join(chunks)
        if self._passes_output_check(request, text, prompt_version):
            self._store(key, semantic, CachedAnswer(text=text, model=metrics.model if metrics else None))

    def _store(self, key: str, semantic: SemanticLookup, answer: CachedAnswer) -> None:
        self._cache.set(key, answer)
        self._semantic.store(semantic, answer)  # reuses the vector embedded by the lookup

    @staticmethod
    def _passes_output_check(request: EstimationRequest, text: str, prompt_version: str) -> bool:
        """Logs a structured warning when the answer breaks the format; such answers are not cacheable."""
        check = check_estimation_output(text, request.language)
        if not check.passed:
            logger.warning(
                "output_check_failed",
                reason=check.reason,
                language=request.language.value,
                prompt_version=prompt_version,
                output_chars=len(text),
            )
        return check.passed
