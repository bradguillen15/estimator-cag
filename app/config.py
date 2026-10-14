from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Provider keys are optional: only the providers actually in use need one (checked by the factory).
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    # Single source of truth for the model and the fallback order: ordered "<provider>/<model>" list (first = primary, the rest = fallbacks).
    # NoDecode lets LLM_MODELS be a plain comma-separated string instead of JSON.
    llm_models: Annotated[list[str], NoDecode] = [
        "anthropic/claude-sonnet-5-5",
        "openai/gpt-4o-mini",
    ]
    llm_timeout: float = 30
    llm_retries: int = 2
    llm_max_tokens: int = 16000
    # Input moderation (OpenAI moderation endpoint via LiteLLM). Needs OPENAI_API_KEY; fails open.
    moderation_enabled: bool = False
    # Exact response cache (Redis). Disabled by default; an unreachable Redis only logs a warning.
    cache_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl: int = 86400
    # Semantic cache (redisvl on Redis Stack + LiteLLM embeddings). LOG_ONLY logs would-be hits
    # without serving them, to calibrate THRESHOLD before turning it on.
    semantic_cache_enabled: bool = False
    semantic_cache_log_only: bool = True
    semantic_cache_threshold: float = 0.92
    semantic_cache_ttl: int = 86400
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dims: int = 1536
    # Conversation sessions (process memory): turns of history replayed to the LLM per session.
    session_max_turns: int = Field(default=6, ge=1)
    # History compression: turns leaving the window are kept verbatim when they carry a commitment
    # (at most this many; the oldest is dropped beyond it) or folded into a bounded running summary.
    session_max_anchors: int = Field(default=5, ge=0)
    session_summary_max_chars: int = Field(default=2000, ge=200)
    # Actor-Critic-Boss (POST /estimate/acb). CRITIC_MODEL is one "<provider>/<model>" entry for the
    # Critic (a cheaper model is fine); empty reuses the LLM_MODELS chain. BOSS_MAX_ITERATIONS is the
    # maximum number of actor attempts (each costs one actor call plus one critic call).
    critic_model: str = ""
    boss_max_iterations: int = Field(default=3, ge=1)
    app_env: str
    log_level: str

    @field_validator("llm_models", mode="before")
    @classmethod
    def _split_llm_models(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


settings = Settings()
