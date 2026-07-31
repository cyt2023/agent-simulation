from __future__ import annotations

import json

import pytest

from study1.services import Study1ServiceError


@pytest.fixture
def study2_service(memory_service):
    from study1.study2_service import Study2ReadOnlyService

    return Study2ReadOnlyService(memory_service)


@pytest.fixture
def study2_session(memory_service):
    created = memory_service.create_session("Study 2 contract")
    session_id = created["session"]["session_id"]
    identities = {
        result["identity"]["role"]: result["identity"]
        for invite in created["invites"]
        for result in [memory_service.exchange_invite(invite["token"])]
    }
    repository = memory_service.repository
    repository.sessions[session_id]["phase"] = "REVIEW"
    repository.materials.extend(
        [
            {
                "session_id": session_id,
                "role": "principal",
                "metadata": {
                    "facts": [
                        {
                            "fact_id": "shared-a",
                            "candidate_id": "a",
                            "text": "Shared evidence.",
                            "visible_to_roles": ["principal", "teammate_1", "teammate_2"],
                        },
                        {
                            "fact_id": "principal-b",
                            "candidate_id": "b",
                            "text": "Principal-only evidence.",
                            "visible_to_roles": ["principal"],
                        },
                    ]
                },
            },
            {
                "session_id": session_id,
                "role": "teammate_1",
                "metadata": {
                    "facts": [
                        {
                            "fact_id": "teammate-c",
                            "candidate_id": "c",
                            "text": "Teammate-only evidence.",
                            "visible_to_roles": ["teammate_1"],
                        }
                    ]
                },
            },
        ]
    )
    repository.artifacts.append(
        {
            "session_id": session_id,
            "artifact_id": "transcript-v1",
            "type": "transcript",
            "version": "1",
            "content": json.dumps(
                [
                    {"segment_id": "u-1", "speaker": "teammate_1", "text": "First utterance."},
                    {"segment_id": "u-2", "speaker": "teammate_2", "text": "Second utterance."},
                ]
            ),
        }
    )
    repository.decisions.extend(
        [
            {
                "session_id": session_id,
                "decision_id": "decision-principal",
                "decision_kind": "pre_individual",
                "participant_id": identities["principal"]["participant_id"],
                "role": "principal",
                "candidate_id": "a",
                "rationale": "Initial independent choice.",
                "confidence": 5,
                "locked": True,
            },
            {
                "session_id": session_id,
                "decision_id": "decision-teammate",
                "decision_kind": "tentative_individual",
                "participant_id": identities["teammate_1"]["participant_id"],
                "role": "teammate_1",
                "candidate_id": "b",
                "rationale": "Delegated discussion choice.",
                "confidence": 4,
                "locked": True,
            },
        ]
    )
    repository.sessions[session_id]["study2_module_telemetry"] = [
        {
            "module_id": "study2.readonly",
            "event_type": "opened",
            "occurred_at": "2026-07-31T00:00:00Z",
            "duration_ms": 40,
            "participant_id": identities["principal"]["participant_id"],
            "secret": "must not leak",
        },
        {
            "module_id": "unapproved.module",
            "event_type": "opened",
            "occurred_at": "2026-07-31T00:00:01Z",
        },
    ]
    return session_id, identities


def test_principal_cannot_read_utterances_while_isolated(
    study2_service, memory_service, study2_session
):
    session_id, identities = study2_session
    memory_service.repository.sessions[session_id]["phase"] = "PROXY_MEETING"

    with pytest.raises(Study1ServiceError) as error:
        study2_service.utterances(session_id, identities["principal"])

    assert error.value.code == "STUDY2_DATA_NOT_AVAILABLE"


def test_read_models_filter_private_facts_decisions_and_module_telemetry(
    study2_service, study2_session
):
    session_id, identities = study2_session

    facts = study2_service.facts(session_id, identities["principal"])
    decisions = study2_service.decisions(session_id, identities["principal"])
    telemetry = study2_service.module_telemetry(session_id, identities["principal"])

    assert [item["fact_id"] for item in facts["items"]] == ["shared-a", "principal-b"]
    assert [item["decision_id"] for item in decisions["items"]] == ["decision-principal"]
    assert telemetry["items"] == [
        {
            "module_id": "study2.readonly",
            "event_type": "opened",
            "occurred_at": "2026-07-31T00:00:00Z",
            "duration_ms": 40,
        }
    ]


def test_read_models_paginate_and_study1_always_disables_resync(
    study2_service, study2_session
):
    session_id, identities = study2_session

    first = study2_service.utterances(session_id, identities["principal"], limit=1)
    second = study2_service.utterances(
        session_id, identities["principal"], cursor=first["next_cursor"], limit=1
    )

    assert [item["utterance_id"] for item in first["items"]] == ["u-1"]
    assert [item["utterance_id"] for item in second["items"]] == ["u-2"]
    assert first["next_cursor"]
    assert study2_service.features(session_id)["resync_enabled"] is False

