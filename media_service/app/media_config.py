from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


MEDIA_CONFIG_VERSION = "study1-media-config-v2"
AUDIO_ONLY_SOURCES = frozenset({"microphone"})
MEDIA_V2_EVENT_TYPES = frozenset(
    {
        "MEDIA_CONFIG_FROZEN",
        "AGENT_TURN_STARTED",
        "AGENT_TURN_COMPLETED",
        "AGENT_TURN_FAILED",
        "RTC_METRIC_BATCH",
        "COMPONENT_HEALTH",
        "RECORDING_TRACK_FINALIZED",
    }
)


class MediaConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderPolicy:
    asr_provider: str = "mock"
    asr_model: str = "study1-asr-v2"
    llm_provider: str = "mock"
    llm_model: str = "study1-proxy-v2"
    tts_provider: str = "mock"
    tts_model: str = "study1-tts-v2"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ProviderPolicy":
        source = value or {}
        return cls(
            asr_provider=str(source.get("asr_provider") or "mock"),
            asr_model=str(source.get("asr_model") or "study1-asr-v2"),
            llm_provider=str(source.get("llm_provider") or "mock"),
            llm_model=str(source.get("llm_model") or "study1-proxy-v2"),
            tts_provider=str(source.get("tts_provider") or "mock"),
            tts_model=str(source.get("tts_model") or "study1-tts-v2"),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "asr_provider": self.asr_provider,
            "asr_model": self.asr_model,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "tts_provider": self.tts_provider,
            "tts_model": self.tts_model,
        }


@dataclass(frozen=True)
class StreamingCapabilities:
    asr: bool = True
    llm: bool = True
    tts: bool = True
    partial_asr: bool = True
    barge_in: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "StreamingCapabilities":
        source = value or {}
        return cls(
            asr=bool(source.get("asr", True)),
            llm=bool(source.get("llm", True)),
            tts=bool(source.get("tts", True)),
            partial_asr=bool(source.get("partial_asr", True)),
            barge_in=bool(source.get("barge_in", True)),
        )

    def to_dict(self) -> dict[str, bool]:
        return {
            "asr": self.asr,
            "llm": self.llm,
            "tts": self.tts,
            "partial_asr": self.partial_asr,
            "barge_in": self.barge_in,
        }


@dataclass(frozen=True)
class FrozenMediaConfig:
    session_id: str
    phase_version: int
    room_name: str
    provider_policy: ProviderPolicy
    streaming: StreamingCapabilities
    publish_sources: tuple[str, ...] = ("microphone",)
    recording_mode: str = "audio_only"
    config_version: str = MEDIA_CONFIG_VERSION

    @classmethod
    def default(cls, *, session_id: str, phase_version: int) -> "FrozenMediaConfig":
        safe_session = str(session_id).replace(":", "-").replace("/", "-")
        return cls(
            session_id=str(session_id),
            phase_version=int(phase_version),
            room_name=f"study1-{safe_session}-audio",
            provider_policy=ProviderPolicy(),
            streaming=StreamingCapabilities(),
        )

    @classmethod
    def from_command(cls, command: Mapping[str, Any]) -> "FrozenMediaConfig":
        payload = command.get("payload")
        if not isinstance(payload, Mapping):
            raise MediaConfigError("media_config payload is required")
        raw_config = payload.get("media_config")
        expected_checksum = payload.get("media_config_checksum")
        if not isinstance(raw_config, Mapping):
            authorized_context = payload.get("authorized_context")
            if isinstance(authorized_context, Mapping):
                raw_config = authorized_context.get("media_config")
                expected_checksum = expected_checksum or authorized_context.get(
                    "media_config_checksum"
                )
        if not isinstance(raw_config, Mapping):
            raise MediaConfigError("media_config is required")
        config = cls.from_mapping(raw_config)
        if expected_checksum and str(expected_checksum) != config.checksum:
            raise MediaConfigError("media_config checksum mismatch")
        return config

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FrozenMediaConfig":
        publish_sources = tuple(str(item) for item in value.get("publish_sources") or ())
        if not publish_sources:
            publish_sources = ("microphone",)
        if any(source not in AUDIO_ONLY_SOURCES for source in publish_sources):
            raise MediaConfigError("Study 1 media config is audio-only")
        recording_mode = str(value.get("recording_mode") or "audio_only")
        if recording_mode != "audio_only":
            raise MediaConfigError("Study 1 media config is audio-only")
        return cls(
            session_id=str(value.get("session_id") or ""),
            phase_version=int(value.get("phase_version") or 1),
            room_name=str(value.get("room_name") or ""),
            provider_policy=ProviderPolicy.from_mapping(value.get("provider_policy")),
            streaming=StreamingCapabilities.from_mapping(value.get("streaming")),
            publish_sources=publish_sources,
            recording_mode=recording_mode,
            config_version=str(value.get("config_version") or MEDIA_CONFIG_VERSION),
        )

    @property
    def checksum(self) -> str:
        return checksum_media_config(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_version": self.config_version,
            "session_id": self.session_id,
            "phase_version": self.phase_version,
            "room_name": self.room_name,
            "recording_mode": self.recording_mode,
            "publish_sources": list(self.publish_sources),
            "provider_policy": self.provider_policy.to_dict(),
            "streaming": self.streaming.to_dict(),
        }


def checksum_media_config(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
