import json

import pytest

from study1.services import Study1ServiceError


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _formal_config():
    return {
        "task_version": "2.0",
        "task_instance_id": "hidden-profile-01",
        "summary_template_version": "study1-five-section-v1",
        "transcript_access_policy": "principal_after_delegation",
        "proxy_model_version": "proxy-model-test",
        "consent_version": "study1-consent-v1",
        "role_assignment_mode": "randomized",
        "randomization_seed": "test-seed",
        "phase_durations_seconds": {"MATERIAL_READING": 600, "PROXY_MEETING": 900},
        "require_consent": True,
        "structured_instruments": True,
    }


def test_formal_session_locks_configuration_atomizes_facts_and_requires_consent(
    memory_service,
):
    created = memory_service.create_session(
        "formal",
        materials_by_role={
            "principal": [{"title": "P", "content": "Shared fact.\nP-only fact."}],
            "teammate_1": [{"title": "T1", "content": "Shared fact.\nT1-only fact."}],
            "teammate_2": [{"title": "T2", "content": "T2-only fact."}],
        },
        experiment_config=_formal_config(),
    )
    session_id = created["session"]["session_id"]
    snapshot = memory_service.repository.get_session(session_id)

    assert snapshot["configuration_locked_at"]
    assert len(snapshot["configuration_checksum"]) == 64
    assert snapshot["task_instance_id"] == "hidden-profile-01"
    materials = memory_service.repository.export_data(session_id)["materials"]
    facts = [
        fact
        for material in materials
        for fact in material["metadata_payload"]["facts"]
    ]
    assert all(
        {
            "fact_id",
            "text",
            "candidate_id",
            "valence",
            "information_type",
            "visible_to_roles",
        }
        <= set(fact)
        for fact in facts
    )
    shared = [fact for fact in facts if fact["text"] == "Shared fact."]
    assert all(fact["information_type"] == "shared" for fact in shared)

    with pytest.raises(Study1ServiceError) as blocked:
        memory_service.control(session_id, RESEARCHER, "start")
    assert blocked.value.code == "PREREQUISITES_NOT_MET"

    identities = [
        memory_service.exchange_invite(invite["token"])["identity"]
        for invite in created["invites"]
    ]
    for identity in identities:
        memory_service.submit(
            session_id,
            identity,
            "consent",
            "2.0",
            {
                "consent_version": "study1-consent-v1",
                "identity_confirmed": True,
                "role_confirmed": True,
                "audio_recording_confirmed": True,
                "voluntary_participation_confirmed": True,
            },
        )
    started = memory_service.control(session_id, RESEARCHER, "start")
    assert started["session"]["phase"] == "MATERIAL_READING"

    with pytest.raises(Study1ServiceError) as missing_reason:
        memory_service.control(session_id, RESEARCHER, "pause")
    assert missing_reason.value.code == "CONTROL_REASON_REQUIRED"
    memory_service.control(
        session_id, RESEARCHER, "pause", {"reason": "scheduled equipment check"}
    )


def test_structured_instrument_rejects_sparse_or_wrong_version_payload(memory_service):
    created = memory_service.create_session(
        "formal-validator",
        experiment_config=_formal_config() | {"require_consent": False},
    )
    session_id = created["session"]["session_id"]
    identity = memory_service.exchange_invite(created["invites"][0]["token"])["identity"]
    memory_service.repository.sessions[session_id]["phase"] = "PRE_VOTE"

    with pytest.raises(Study1ServiceError) as wrong_version:
        memory_service.submit(
            session_id, identity, "pre_vote", "1.0", {"decision": "A"}
        )
    assert wrong_version.value.code == "INSTRUMENT_VERSION_REQUIRED"

    with pytest.raises(Study1ServiceError) as incomplete:
        memory_service.submit(
            session_id, identity, "pre_vote", "2.0", {"decision": "A"}
        )
    assert incomplete.value.code == "INCOMPLETE_INSTRUMENT"


def test_transcript_correction_is_append_only_and_preserves_original(memory_service):
    created = memory_service.create_session("correction")
    session_id = created["session"]["session_id"]
    transcript = json.dumps(
        [{"segment_id": "seg-1", "speaker": "teammate_1", "text": "wrong words"}]
    )
    memory_service.create_artifact(
        session_id,
        {
            "type": "transcript",
            "version": "1",
            "content": transcript,
            "generator_version": "mock-asr",
        },
    )

    correction = memory_service.create_transcript_correction(
        session_id,
        RESEARCHER,
        "seg-1",
        "correct words",
        "researcher verified against audio",
    )
    payload = json.loads(correction["artifact"]["content"])
    assert payload["original_text"] == "wrong words"
    assert payload["corrected_text"] == "correct words"
    artifacts = memory_service.repository.export_data(session_id)["artifacts"]
    assert [item["type"] for item in artifacts] == [
        "transcript",
        "transcript_correction",
    ]
