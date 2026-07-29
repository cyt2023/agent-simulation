import hashlib
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone

from flask import Flask

from routes.session import session_bp
from study1.routes import study1_bp


RESEARCHER = {"participant_id": "researcher", "role": "researcher"}


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _artifact(service, session_id, artifact_type, content):
    service.create_artifact(
        session_id,
        {
            "artifact_id": str(uuid.uuid4()),
            "type": artifact_type,
            "version": "1",
            "content": content,
            "checksum": hashlib.sha256(content.encode()).hexdigest(),
            "generator_version": "mock-e2e",
        },
    )


def _media(service, session_id, event_type):
    snapshot = service.repository.sessions[session_id]
    service.receive_media_event(
        {
            "event_id": str(uuid.uuid4()),
            "session_id": session_id,
            "phase_version": snapshot["phase_version"],
            "event_type": event_type,
            "occurred_at": _now(),
            "payload": {"source": "mock-e2e"},
        }
    )


def test_complete_mock_study1_flow_and_export(memory_service):
    created = memory_service.create_session(
        "complete-flow",
        materials_by_role={
            "principal": [{"title": "P", "content": "P private"}],
            "teammate_1": [{"title": "T1", "content": "T1 private"}],
            "teammate_2": [{"title": "T2", "content": "T2 private"}],
        },
    )
    session_id = created["session"]["session_id"]
    identities = {}
    for invite in created["invites"]:
        exchanged = memory_service.exchange_invite(invite["token"])
        identities[invite["role"]] = exchanged["identity"]

    memory_service.control(session_id, RESEARCHER, "start")
    for identity in identities.values():
        assert len(memory_service.get_materials(session_id, identity["role"])) == 1
        memory_service.submit(
            session_id, identity, "material_ack", "ack-v1", {"acknowledged": True}
        )
    memory_service.advance(session_id, RESEARCHER, "PRE_VOTE")
    for identity in identities.values():
        memory_service.submit(
            session_id,
            identity,
            "pre_vote",
            "vote-v1",
            {"decision": "candidate-a"},
        )

    memory_service.advance(session_id, RESEARCHER, "PROXY_CONFIGURATION")
    principal_material_id = memory_service.get_materials(
        session_id, "principal"
    )[0]["material_id"]
    memory_service.submit(
        session_id,
        identities["principal"],
        "proxy_config",
        "proxy-v1",
        {
            "priorities": "accuracy",
            "authorization_confirmed": True,
            "authorized_material_ids": [principal_material_id],
        },
    )
    for role in ("teammate_1", "teammate_2"):
        memory_service.submit(
            session_id,
            identities[role],
            "proxy_ready",
            "ready-v1",
            {"ready": True},
        )

    memory_service.advance(session_id, RESEARCHER, "PROXY_MEETING")
    memory_service.issue_media_command(
        session_id, RESEARCHER, "START_PROXY_MEETING"
    )
    _media(memory_service, session_id, "MEETING_ENDED")
    memory_service.advance(session_id, RESEARCHER, "TENTATIVE_DECISION")
    for role in ("teammate_1", "teammate_2"):
        memory_service.submit(
            session_id,
            identities[role],
            "tentative_decision",
            "tentative-v1",
            {"decision": "candidate-a", "rationale": "evidence"},
        )

    memory_service.advance(session_id, RESEARCHER, "DELEGATION_EXPECTATION")
    memory_service.submit(
        session_id,
        identities["principal"],
        "delegation_expectation",
        "expectation-v1",
        {"response": "I expect the group to select A"},
    )
    _artifact(memory_service, session_id, "summary", "Neutral mock summary")
    _artifact(
        memory_service,
        session_id,
        "transcript",
        "Mock segment one\nMock segment two",
    )

    memory_service.advance(session_id, RESEARCHER, "REVIEW")
    review = memory_service.get_review(session_id, identities["principal"])
    assert review["summary"]["content"] == "Neutral mock summary"
    memory_service.log_review_ui_event(
        session_id,
        identities["principal"],
        "scroll_depth",
        {"max_depth": 1, "visible_segments": ["segment-1"]},
    )
    memory_service.advance(
        session_id, RESEARCHER, "COMPREHENSION_MEASUREMENT"
    )
    memory_service.submit(
        session_id,
        identities["principal"],
        "comprehension_measurement",
        "comprehension-v1",
        {"response": "understanding recorded"},
    )

    memory_service.advance(session_id, RESEARCHER, "HANDOFF")
    memory_service.issue_media_command(session_id, RESEARCHER, "BEGIN_HANDOFF")
    _media(memory_service, session_id, "HANDOFF_COMPLETE")
    memory_service.advance(session_id, RESEARCHER, "SYNC_MEETING")
    memory_service.issue_media_command(
        session_id, RESEARCHER, "START_SYNC_MEETING"
    )
    _media(memory_service, session_id, "MEETING_ENDED")

    memory_service.advance(session_id, RESEARCHER, "FINAL_DECISION")
    for identity in identities.values():
        memory_service.submit(
            session_id,
            identity,
            "final_decision",
            "final-v1",
            {"decision": "candidate-a"},
        )
    memory_service.advance(session_id, RESEARCHER, "FOLLOWUP_TASK")
    for identity in identities.values():
        memory_service.submit(
            session_id,
            identity,
            "followup_task",
            "followup-v1",
            {"response": "complete"},
        )
    memory_service.advance(session_id, RESEARCHER, "POST_SURVEY")
    for identity in identities.values():
        memory_service.submit(
            session_id,
            identity,
            "post_survey",
            "survey-v1",
            {"response": "complete"},
        )
    completed = memory_service.advance(session_id, RESEARCHER, "COMPLETED")
    assert completed["session"]["status"] == "completed"
    assert completed["session"]["phase"] == "COMPLETED"

    export_buffer = memory_service.export_bundle(session_id)
    with zipfile.ZipFile(export_buffer) as archive:
        assert set(archive.namelist()) == {
            "session.json",
            "participants.csv",
            "phase_events.csv",
            "submissions.jsonl",
            "ui_events.jsonl",
            "incidents.csv",
            "artifacts_manifest.json",
            "materials_assignment.json",
            "schema_version.json",
            "integrity_report.json",
        }
        schema = json.loads(archive.read("schema_version.json"))
        assert schema["protocol_version"] == "study1-a-1.0"
        assert schema["phase_schema_version"] == "1.0"
        assert schema["missing_data"]["submissions"] == []
        assert schema["missing_data"]["artifacts"] == []


def test_legacy_non_study1_routes_still_register():
    app = Flask(__name__)
    app.register_blueprint(session_bp)
    app.register_blueprint(study1_bp)
    rules = {str(rule) for rule in app.url_map.iter_rules()}
    assert "/api/sessions" in rules
    assert "/api/experiments" in rules
    assert "/api/study1/sessions" in rules


def test_frontend_router_keeps_legacy_routes():
    with open("frontend/src/router/index.js", encoding="utf-8") as source:
        router = source.read()
    for path in (
        "path: '/participant'",
        "path: '/researcher'",
        "path: '/study1/participant'",
        "path: '/researcher/study1'",
    ):
        assert path in router
