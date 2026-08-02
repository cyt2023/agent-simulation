"""Study 1 privacy vocabulary.

The research protocol treats consent and operator authorization as explicit
scopes.  The vocabulary is intentionally small and audio-only: there is no
video scope in Study 1.
"""

from __future__ import annotations

from dataclasses import dataclass


CONSENT_SCOPES: tuple[str, ...] = (
    "audio_recording",
    "transcription",
    "ui_telemetry",
    "external_agent_processing",
)

RESEARCHER_SCOPES: tuple[str, ...] = (
    "operate",
    "export_analysis",
    "read_raw_media",
    "quality_audit",
    "privacy_admin",
)

DEFAULT_RESEARCHER_SCOPES: frozenset[str] = frozenset(
    {"operate", "export_analysis", "quality_audit"}
)


@dataclass(frozen=True)
class ConsentScopeState:
    session_id: str
    participant_id: str
    role: str
    scope: str
    granted: bool
    consent_version: str | None = None
    recorded_at: str | None = None

    def public_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "participant_id": self.participant_id,
            "role": self.role,
            "scope": self.scope,
            "granted": self.granted,
            "consent_version": self.consent_version,
            "recorded_at": self.recorded_at,
        }
