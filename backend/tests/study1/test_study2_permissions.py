from __future__ import annotations

from flask import Flask


def test_versioned_contract_returns_etag_and_honors_if_none_match(
    monkeypatch, memory_service, token_manager
):
    from study1.study2_routes import set_study2_service_for_testing, study2_bp
    from study1.study2_service import Study2ReadOnlyService

    monkeypatch.setenv("STUDY1_TOKEN_SECRET", "test-only-secret")
    created = memory_service.create_session("ETag contract")
    session_id = created["session"]["session_id"]
    invite = next(item for item in created["invites"] if item["role"] == "principal")
    identity = memory_service.exchange_invite(invite["token"])["identity"]
    memory_service.repository.materials.append(
        {
            "session_id": session_id,
            "role": "principal",
            "metadata": {
                "facts": [
                    {
                        "fact_id": "p-a",
                        "candidate_id": "a",
                        "text": "Visible fact.",
                        "visible_to_roles": ["principal"],
                    }
                ]
            },
        }
    )
    app = Flask(__name__)
    app.register_blueprint(study2_bp)
    set_study2_service_for_testing(Study2ReadOnlyService(memory_service))
    headers = {"Authorization": f"Bearer {token_manager.issue_participant(session_id, identity['participant_id'], identity['role'])}"}
    try:
        client = app.test_client()
        first = client.get(f"/api/study2/v1/sessions/{session_id}/facts", headers=headers)
        second = client.get(
            f"/api/study2/v1/sessions/{session_id}/facts",
            headers={**headers, "If-None-Match": first.headers["ETag"]},
        )
    finally:
        set_study2_service_for_testing(None)

    assert first.status_code == 200
    assert first.get_json()["contract_version"] == "study2-readonly-contract-v1"
    assert first.headers["ETag"]
    assert second.status_code == 304


def test_formal_protocol_rejects_module_ids_as_well_as_enabled_resync():
    import pytest

    from study1.protocol_config import (
        ProtocolConfigError,
        formal_protocol_defaults,
        normalize_protocol_config_v2,
    )

    with pytest.raises(ProtocolConfigError) as resync:
        normalize_protocol_config_v2(
            formal_protocol_defaults() | {"feature_flags": {"resync_enabled": True, "video_enabled": False}}
        )
    with pytest.raises(ProtocolConfigError) as module:
        normalize_protocol_config_v2(formal_protocol_defaults() | {"module_id": "study2.readonly"})

    assert resync.value.code == "RESYNC_DISABLED"
    assert module.value.code == "MODULE_ID_NOT_ALLOWED"
