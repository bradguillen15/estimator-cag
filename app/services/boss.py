"""The Boss: pure orchestration of the Actor-Critic loop.

No SDK, no HTTP, no prompts: it only decides what to do next, so every decision is traceable in the
returned trail and testable with plain callables.

    actor(None) -> critic -> decide
        accept                          -> return the estimate
        needs_iteration, budget left    -> actor(feedback) -> critic -> ...
        needs_iteration, budget spent   -> return the last estimate, flagged ``needs_iteration``
        reject                          -> stop at once, return the last estimate, flagged ``reject``

The estimate is never discarded: the caller gets the best available draft plus the verdict that says
whether the Critic still disputes it.
"""

from collections.abc import Callable
from dataclasses import dataclass

import structlog

from app.schemas.acb import AcbIteration
from app.schemas.critic import CriticFeedback, CriticVerdict

logger = structlog.get_logger()

DEFAULT_MAX_ITERATIONS = 3

Actor = Callable[[CriticFeedback | None], str]
Critic = Callable[[str], CriticFeedback]


@dataclass(frozen=True)
class BossResult:
    estimate: str
    final_verdict: CriticVerdict
    iterations: list[AcbIteration]


class Boss:
    def __init__(self, max_iterations: int = DEFAULT_MAX_ITERATIONS) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1.")
        self._max_iterations = max_iterations

    def run(self, actor: Actor, critic: Critic) -> BossResult:
        """Runs at most ``max_iterations`` actor attempts (so at most twice as many LLM calls)."""
        trail: list[AcbIteration] = []
        feedback: CriticFeedback | None = None
        for attempt in range(1, self._max_iterations + 1):
            estimate = actor(feedback)
            review = critic(estimate)
            trail.append(AcbIteration(attempt=attempt, verdict=review.verdict, issues=review.issues))
            logger.info("boss_iteration", attempt=attempt, verdict=review.verdict, issues=len(review.issues))
            if review.verdict != "needs_iteration":
                return BossResult(estimate, review.verdict, trail)
            feedback = review
        logger.info("boss_budget_exhausted", attempts=self._max_iterations)
        return BossResult(estimate, "needs_iteration", trail)
