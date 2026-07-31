"""Stable incident code catalog for Study 1."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IncidentDefinition:
    code: str
    label: str
    component: str
    default_severity: str = "warning"


INCIDENT_CATALOG: dict[str, IncidentDefinition] = {
    item.code: item
    for item in (
        IncidentDefinition(
            "participant_disconnect", "Participant disconnect", "rtc"
        ),
        IncidentDefinition("recorder_failure", "Recorder failure", "recording"),
        IncidentDefinition("asr_provider_error", "ASR provider error", "asr"),
        IncidentDefinition("llm_provider_error", "LLM provider error", "llm"),
        IncidentDefinition("tts_provider_error", "TTS provider error", "tts"),
        IncidentDefinition(
            "summary_generation_failed", "Summary generation failed", "summary"
        ),
        IncidentDefinition(
            "callback_delivery_failed", "Callback delivery failed", "callback"
        ),
        IncidentDefinition("permission_denied", "Permission denied", "permission"),
        IncidentDefinition("protocol_violation", "Protocol violation", "protocol"),
    )
}


class IncidentCodeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def incident_definition(code: str) -> IncidentDefinition:
    clean = str(code or "").strip()
    definition = INCIDENT_CATALOG.get(clean)
    if definition is None:
        raise IncidentCodeError(
            "INVALID_INCIDENT_CODE", "Incident category must use the coded catalog"
        )
    return definition
