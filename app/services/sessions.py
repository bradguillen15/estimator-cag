"""Conversation sessions: a sliding-window history plus the facts of the project being estimated.

History and memory are kept apart on purpose:

- ``ConversationHistory`` is *what was said*: the recent ``user``/``assistant`` messages replayed
  to the LLM on every call, trimmed to the last N turns so the token bill stays bounded.
- ``ProjectMetadata`` is *what we know*: the project facts that must survive even after the turn
  that mentioned them falls out of the window. It is rendered into the system prompt.

The system prompt itself is never stored here: it is rendered per request (a cacheable static
prefix plus trailing blocks such as the metadata), so the window can never trim it away.

Sessions live in a process-local dict. That volatility is accepted in this phase: the service
runs as a single process with no replicas, and a session is a short working conversation, so
losing it on a restart costs one re-sent description. Persistence (e.g. Redis) comes when there
is more than one worker or sessions must outlive a deploy.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from app.exceptions import SessionNotFoundError
from app.schemas.sessions import ProjectMetadata

Role = Literal["user", "assistant"]
DEFAULT_MAX_TURNS = 6  # SESSION_MAX_TURNS overrides it


class ConversationHistory:
    """The last ``max_turns`` turns (one turn = a user message and the assistant reply).

    Older messages are dropped as a whole turn, so the window never starts with an orphan reply.
    """

    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        self.max_turns = max_turns
        self._messages: list[dict[str, str]] = []

    def add_turn(self, user_content: str, assistant_content: str) -> None:
        self._messages.append({"role": "user", "content": user_content})
        self._messages.append({"role": "assistant", "content": assistant_content})
        overflow = len(self._messages) - 2 * self.max_turns
        if overflow > 0:
            del self._messages[:overflow]

    def to_messages_list(self, system_prompt: str) -> list[dict[str, str]]:
        """The ``messages`` array for the LLM: the system prompt, then the kept turns.

        The system prompt is passed in on every call rather than stored, so it is always present
        (never trimmed) and always rebuilt from the current ``project_metadata``. The caller
        appends the new user message.
        """
        return [{"role": "system", "content": system_prompt}, *self.messages]

    @property
    def messages(self) -> list[dict[str, str]]:
        """A copy in chronological order, ready to go after the system message of an LLM call."""
        return [dict(message) for message in self._messages]

    def __len__(self) -> int:
        """The number of complete turns kept."""
        return len(self._messages) // 2


@dataclass
class Session:
    session_id: str
    history: ConversationHistory
    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SessionStore:
    """Process-local registry of sessions by ``session_id`` (see the module docstring on volatility).

    Sync handlers run in FastAPI's threadpool, so access to the dict is guarded by a lock.
    """

    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS) -> None:
        self._max_turns = max_turns
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self) -> Session:
        session = Session(
            session_id=str(uuid.uuid4()),
            history=ConversationHistory(self._max_turns),
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError("La sesión no existe o ha expirado. Crea una nueva.")
        return session
