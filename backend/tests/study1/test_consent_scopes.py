from __future__ import annotations

import pytest


SCOPES = (
    "audio_recording",
    "transcription",
    "ui_telemetry",
    "external_agent_processing",
)


@pytest.mark.parametrize("scope", SCOPES)
def test_each_consent_scope_is_recorded_separately(scope):
    from study1.privacy_service import InMemoryConsentStore, PrivacyService

    service = PrivacyService(InMemoryConsentStore())
    participant = {
        "session_id": "session-1",
        "participant_id": "participant-1",
        "role": "principal",
    }

    service.record_consent(participant, {scope: True}, version="consent-v2")

    assert service.scope_state(participant, scope)["granted"] is True
    denied = [item for item in SCOPES if item != scope]
    assert [
        service.scope_state(participant, item)["granted"] for item in denied
    ] == [False, False, False]


def test_normalized_consent_never_adds_video_scope():
    from study1.privacy_service import normalize_consent_scopes

    scopes = normalize_consent_scopes(
        {
            "audio_recording": True,
            "transcription": True,
            "ui_telemetry": True,
            "external_agent_processing": True,
            "video_recording": True,
        }
    )

    assert set(scopes) == set(SCOPES)
    assert "video_recording" not in scopes


def test_formal_consent_submission_persists_separate_scopes(memory_service):
    created = memory_service.create_session(
        "scoped consent",
        experiment_config={"require_consent": True, "structured_instruments": True},
    )
    session_id = created["session"]["session_id"]
    principal = memory_service.exchange_invite(created["invites"][0]["token"])[
        "identity"
    ]
    assert principal["role"] == "principal"
    payload = {
        "consent_version": "consent-v2",
        "identity_confirmed": True,
        "role_confirmed": True,
        "voluntary_participation_confirmed": True,
        "consent_scopes": {
            "audio_recording": True,
            "transcription": True,
            "ui_telemetry": True,
            "external_agent_processing": True,
        },
    }

    submission = memory_service.submit(
        session_id, principal, "consent", "2.0", payload
    )

    assert submission["payload"]["consent_scopes"] == payload["consent_scopes"]
    assert "video_recording" not in submission["payload"]["consent_scopes"]
