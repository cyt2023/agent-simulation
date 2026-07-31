from __future__ import annotations

import pytest


def test_release_rejects_unknown_build():
    from scripts.build_study1_release_manifest import ReleaseError, build_release_manifest

    with pytest.raises(ReleaseError, match="unknown"):
        build_release_manifest({"backend_build": "unknown"})


def test_technical_acceptance_cannot_claim_data_collection_ready_without_signoffs():
    from scripts.build_study1_release_manifest import build_release_manifest
    from scripts.verify_study1_release import verify_release_manifest

    manifest = build_release_manifest(
        {
            "release_id": "study1-local-test",
            "backend_build": "backend-test",
            "frontend_build": "frontend-test",
            "media_build": "media-test",
            "requested_status": "data_collection_ready",
            "external_signoffs": {
                "irb_approval": False,
                "production_wss_turn": False,
                "production_credentials": False,
                "real_participant_pilots": False,
            },
        }
    )

    result = verify_release_manifest(manifest)

    assert result.status == "technical_acceptance"
    assert "EXTERNAL_SIGNOFFS_INCOMPLETE" in result.warnings
    assert manifest["acceptance"]["status"] == "technical_acceptance"


def test_release_manifest_records_core_versions_and_hashes():
    from scripts.build_study1_release_manifest import build_release_manifest

    manifest = build_release_manifest(
        {
            "release_id": "study1-release-v1",
            "backend_build": "backend-sha",
            "frontend_build": "frontend-sha",
            "media_build": "media-sha",
            "protocol": {
                "protocol_version": "study1-audio-formal-v2",
                "task_version": "2.0",
                "task_instance_id": "hidden-profile-001",
                "task_checksum": "task-sha",
                "facts_checksum": "facts-sha",
            },
            "providers": {
                "llm": {"provider": "openai", "model": "gpt-4o-mini"},
                "asr": {"provider": "openai", "model": "gpt-4o-transcribe"},
                "tts": {"provider": "openai", "model": "gpt-4o-mini-tts"},
            },
        }
    )

    assert manifest["schema_version"] == "study1-release-v1"
    assert manifest["build_versions"]["backend"] == "backend-sha"
    assert manifest["protocol"]["facts_checksum"] == "facts-sha"
    assert manifest["providers"]["llm"]["model"] == "gpt-4o-mini"
    assert len(manifest["checksum"]) == 64


def test_release_manifest_records_audio_e2e_gate():
    from scripts.build_study1_release_manifest import build_release_manifest

    manifest = build_release_manifest(
        {
            "release_id": "study1-release-v1",
            "backend_build": "backend-sha",
            "frontend_build": "frontend-sha",
            "media_build": "media-sha",
        }
    )

    commands = {
        gate["command"]
        for gate in manifest["acceptance"]["automated_gates"]
    }

    assert "npm.cmd run test:e2e" in commands


def test_release_manifest_records_release_self_checks():
    from scripts.build_study1_release_manifest import build_release_manifest

    manifest = build_release_manifest(
        {
            "release_id": "study1-release-v1",
            "backend_build": "backend-sha",
            "frontend_build": "frontend-sha",
            "media_build": "media-sha",
        }
    )

    commands = [
        gate["command"]
        for gate in manifest["acceptance"]["automated_gates"]
    ]

    assert commands[:2] == [
        "python scripts/build_study1_release_manifest.py --output release/study1-release-manifest.json",
        "python scripts/verify_study1_release.py release/study1-release-manifest.json",
    ]


def test_a_adds_release_identity_to_media_commands(memory_service, monkeypatch):
    monkeypatch.setenv("STUDY1_RELEASE_ID", "study1-release-v1")
    monkeypatch.setenv("STUDY1_RELEASE_CHECKSUM", "abc123")
    researcher = {"participant_id": "researcher", "role": "researcher"}
    created = memory_service.create_session("release media command")
    session_id = created["session"]["session_id"]
    memory_service.repository.sessions[session_id]["phase"] = "PROXY_MEETING"
    memory_service.repository.sessions[session_id]["phase_version"] = 5

    result = memory_service.issue_media_command(
        session_id, researcher, "END_CURRENT_MEETING"
    )

    assert result["command"]["payload"]["release"] == {
        "release_id": "study1-release-v1",
        "checksum": "abc123",
    }
