"""Consent scope and privacy authorization helpers for Study 1."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Mapping

from .privacy_models import CONSENT_SCOPES, ConsentScopeState


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_consent_scopes(value: Mapping[str, Any] | None) -> dict[str, bool]:
    """Return the canonical audio-only consent map.

    Unknown keys are ignored so clients cannot smuggle a video scope into the
    protocol record.
    """

    raw = value or {}
    return {scope: raw.get(scope) is True for scope in CONSENT_SCOPES}


def consent_scopes_from_submission(payload: Mapping[str, Any]) -> dict[str, bool]:
    """Normalize current and legacy consent payloads.

    Legacy Study 1 builds had one combined audio/transcript/export checkbox.
    When that flag is present, it is expanded to the four Study 1 audio-only
    scopes for backward compatibility.
    """

    if isinstance(payload.get("consent_scopes"), Mapping):
        return normalize_consent_scopes(payload["consent_scopes"])
    legacy_granted = payload.get("audio_recording_confirmed") is True
    return {scope: legacy_granted for scope in CONSENT_SCOPES}


def normalize_consent_submission(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(payload))
    result["consent_scopes"] = consent_scopes_from_submission(result)
    return result


def missing_required_consent_scopes(payload: Mapping[str, Any]) -> list[str]:
    scopes = consent_scopes_from_submission(payload)
    return [scope for scope, granted in scopes.items() if not granted]


class InMemoryConsentStore:
    def __init__(self):
        self.rows: list[ConsentScopeState] = []

    def append(self, state: ConsentScopeState) -> None:
        self.rows.append(state)

    def latest(
        self, session_id: str, participant_id: str, scope: str
    ) -> ConsentScopeState | None:
        matches = [
            row
            for row in self.rows
            if row.session_id == session_id
            and row.participant_id == participant_id
            and row.scope == scope
        ]
        return matches[-1] if matches else None


class PrivacyService:
    def __init__(self, store: InMemoryConsentStore | None = None):
        self.store = store or InMemoryConsentStore()

    def record_consent(
        self,
        participant: Mapping[str, Any],
        scopes: Mapping[str, Any],
        *,
        version: str,
    ) -> dict[str, Any]:
        normalized = normalize_consent_scopes(scopes)
        recorded_at = _utc_iso()
        states = []
        for scope, granted in normalized.items():
            state = ConsentScopeState(
                session_id=str(participant.get("session_id") or ""),
                participant_id=str(participant.get("participant_id") or ""),
                role=str(participant.get("role") or ""),
                scope=scope,
                granted=granted,
                consent_version=str(version or ""),
                recorded_at=recorded_at,
            )
            self.store.append(state)
            states.append(state.public_dict())
        return {"consent_scopes": states}

    def scope_state(
        self, participant: Mapping[str, Any], scope: str
    ) -> dict[str, Any]:
        if scope not in CONSENT_SCOPES:
            raise ValueError(f"Unknown consent scope: {scope}")
        state = self.store.latest(
            str(participant.get("session_id") or ""),
            str(participant.get("participant_id") or ""),
            scope,
        )
        if state is None:
            state = ConsentScopeState(
                session_id=str(participant.get("session_id") or ""),
                participant_id=str(participant.get("participant_id") or ""),
                role=str(participant.get("role") or ""),
                scope=scope,
                granted=False,
            )
        return state.public_dict()
