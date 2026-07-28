from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MediaCommand(StrEnum):
    START_PROXY_MEETING = "START_PROXY_MEETING"
    END_CURRENT_MEETING = "END_CURRENT_MEETING"
    BEGIN_HANDOFF = "BEGIN_HANDOFF"
    START_SYNC_MEETING = "START_SYNC_MEETING"
    REGENERATE_SUMMARY = "REGENERATE_SUMMARY"
    STOP_SESSION = "STOP_SESSION"


class RuntimeState(StrEnum):
    IDLE = "IDLE"
    PREPARING = "PREPARING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    ENDING = "ENDING"
    PROCESSING = "PROCESSING"
    HANDING_OFF = "HANDING_OFF"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class CommandEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    phase_version: int = Field(ge=1)
    command: MediaCommand
    issued_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("issued_at")
    @classmethod
    def issued_at_must_include_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("issued_at must include a timezone")
        return value


class CommandAcceptance(BaseModel):
    accepted: bool = True
    duplicate: bool
    command_id: str
    runtime_state: RuntimeState


class MediaAccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    phase: str
    phase_version: int = Field(ge=1)
    role: str
    participant_id: str


class MediaAccessResponse(BaseModel):
    room_name: str
    url: str
    token: str
    expires_at: datetime
    captions_enabled: bool = False


class DeviceStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    phase_version: int = Field(ge=1)
    participant_id: str
    role: str
    state: str
    device: dict[str, Any] = Field(default_factory=dict)
