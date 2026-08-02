from __future__ import annotations

import copy

import pytest

from study1.models import Study1Phase
from study1.services import Study1ServiceError


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _task(task_definition_id: str = "protocol-task") -> dict:
    return {
        "task_definition_id": task_definition_id,
        "task_version": "1.0",
        "title": "Protocol freeze task",
        "candidate_ids": ["a", "b", "c"],
        "facts": [
            {
                "fact_id": "shared-a",
                "candidate_id": "a",
                "text": "Shared evidence for A.",
                "valence": "positive",
                "information_type": "shared",
                "visible_to_roles": ["principal", "teammate_1", "teammate_2"],
            },
            {
                "fact_id": "p-b",
                "candidate_id": "b",
                "text": "Private evidence for P.",
                "valence": "positive",
                "information_type": "unique",
                "visible_to_roles": ["principal"],
            },
            {
                "fact_id": "t1-c",
                "candidate_id": "c",
                "text": "Private evidence for T1.",
                "valence": "negative",
                "information_type": "unique",
                "visible_to_roles": ["teammate_1"],
            },
            {
                "fact_id": "t2-b",
                "candidate_id": "b",
                "text": "Private evidence for T2.",
                "valence": "positive",
                "information_type": "unique",
                "visible_to_roles": ["teammate_2"],
            },
        ],
    }


def _formal_session(service, task_definition_id: str = "protocol-task"):
    task = service.create_task_definition(RESEARCHER, _task(task_definition_id))
    service.validate_task_definition(task_definition_id, RESEARCHER, task["task_version"])
    return service.create_session(
        "Formal protocol",
        task_definition_id=task_definition_id,
        experiment_config={
            "randomization_seed": "stable-seed",
            "laboratory_timezone": "Asia/Shanghai",
        },
    )


def test_protocol_requires_every_phase_duration_and_audio_only_mode():
    from study1.protocol_config import ProtocolConfigError, normalize_protocol_config_v2

    with pytest.raises(ProtocolConfigError) as missing:
        normalize_protocol_config_v2({"recording_mode": "audio_only"})
    assert missing.value.code == "MISSING_PHASE_DURATIONS"

    durations = {phase.value: 0 for phase in Study1Phase}
    with pytest.raises(ProtocolConfigError) as video:
        normalize_protocol_config_v2(
            {
                "phase_durations_seconds": durations,
                "recording_mode": "audio_video",
            }
        )
    assert video.value.code == "AUDIO_ONLY_REQUIRED"


def test_protocol_canonical_json_and_checksum_are_order_independent():
    from study1.protocol_config import (
        canonical_protocol_json,
        compute_protocol_checksum,
        formal_protocol_defaults,
        normalize_protocol_config_v2,
    )

    first = normalize_protocol_config_v2(formal_protocol_defaults())
    shuffled = dict(reversed(list(copy.deepcopy(first).items())))

    assert canonical_protocol_json(first) == canonical_protocol_json(shuffled)
    assert compute_protocol_checksum(first) == compute_protocol_checksum(shuffled)


@pytest.mark.parametrize("service_fixture", ["memory_service", "sql_service"])
def test_formal_protocol_snapshot_freezes_at_start_and_blocks_mutation(
    request, service_fixture
):
    service = request.getfixturevalue(service_fixture)
    created = _formal_session(service, f"{service_fixture}-protocol")
    session_id = created["session"]["session_id"]
    before = service.get_protocol_snapshot(session_id)

    assert before["protocol_mode"] == "formal_v2"
    assert before["frozen"] is False
    assert before["canonical_config"]["recording_mode"] == "audio_only"
    assert before["canonical_config"]["feature_flags"]["resync_enabled"] is False

    updated = service.update_protocol_config(
        session_id,
        RESEARCHER,
        {"minimum_review_seconds": 37, "laboratory_timezone": "UTC"},
    )
    assert updated["canonical_config"]["minimum_review_seconds"] == 37

    service.control(session_id, RESEARCHER, "start")
    frozen = service.get_protocol_snapshot(session_id)
    assert frozen["frozen"] is True
    assert frozen["frozen_at"]
    assert len(frozen["checksum"]) == 64

    with pytest.raises(Study1ServiceError) as material_error:
        service.add_materials(
            session_id,
            "principal",
            [{"title": "Late", "content": "Late material."}],
        )
    assert material_error.value.code == "CONFIGURATION_FROZEN"

    with pytest.raises(Study1ServiceError) as config_error:
        service.update_protocol_config(
            session_id, RESEARCHER, {"minimum_review_seconds": 45}
        )
    assert config_error.value.code == "CONFIGURATION_FROZEN"


def test_runtime_config_mismatch_is_rejected(memory_service):
    from study1.protocol_config import assert_protocol_runtime_match

    created = _formal_session(memory_service, "runtime-match-task")
    session_id = created["session"]["session_id"]
    memory_service.control(session_id, RESEARCHER, "start")
    snapshot = memory_service.get_protocol_snapshot(session_id)

    with pytest.raises(Study1ServiceError) as error:
        assert_protocol_runtime_match(snapshot, {"backend": "different-build"})
    assert error.value.code == "PROTOCOL_RUNTIME_MISMATCH"


def test_clone_preserves_protocol_values_but_changes_randomization_seed(memory_service):
    created = _formal_session(memory_service, "clone-protocol-task")
    session_id = created["session"]["session_id"]
    source = memory_service.get_protocol_snapshot(session_id)["canonical_config"]

    clone = memory_service.clone_session(session_id, "Cloned formal protocol")
    cloned = memory_service.get_protocol_snapshot(clone["session"]["session_id"])[
        "canonical_config"
    ]

    assert cloned["randomization_seed"] != source["randomization_seed"]
    assert {
        key: value for key, value in cloned.items() if key != "randomization_seed"
    } == {key: value for key, value in source.items() if key != "randomization_seed"}
