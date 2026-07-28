from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "media_service/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    media_database_url: str
    media_database_schema: str = "study1_media"
    a_to_b_service_token: str = Field(min_length=1)
    study1_internal_api_key: str = Field(min_length=1)
    a_base_url: str = "http://backend:5000"
    livekit_url: str = "ws://livekit:7880"
    livekit_public_url: str | None = None
    livekit_api_key: str = Field(min_length=1)
    livekit_api_secret: str = Field(min_length=1)
    livekit_token_ttl_seconds: int = Field(default=300, ge=60, le=900)
    media_root: str = "/app/media"
    captions_enabled: bool = False
    media_provider: str = "mock"
    openai_api_key: str | None = None
    openai_llm_model: str = "gpt-4o-mini"
    openai_asr_model: str = "whisper-1"
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "alloy"
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_whisper_deployment: str = "whisper"
    azure_tts_deployment: str = "tts"
    proxy_prompt_version: str = "proxy-v1"
    summary_prompt_version: str = "neutral-summary-v1"
    callback_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    callback_poll_seconds: float = Field(default=2.0, ge=0.25, le=30)

    @model_validator(mode="after")
    def reject_production_placeholders(self):
        if self.media_database_url.startswith("sqlite"):
            return self
        sensitive = {
            "A_TO_B_SERVICE_TOKEN": self.a_to_b_service_token,
            "STUDY1_INTERNAL_API_KEY": self.study1_internal_api_key,
            "LIVEKIT_API_SECRET": self.livekit_api_secret,
        }
        for name, value in sensitive.items():
            lowered = value.casefold()
            if (
                len(value) < 32
                or "change-me" in lowered
                or lowered in {"secret", "password", "devsecret"}
            ):
                raise ValueError(
                    f"{name} must be a non-placeholder secret of at least 32 characters"
                )
        if self.livekit_api_key.casefold() in {"devkey", "change-me"}:
            raise ValueError("LIVEKIT_API_KEY must not use a placeholder value")
        return self
