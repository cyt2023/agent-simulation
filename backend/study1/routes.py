"""HTTP boundary for Study 1 only."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from flask import Blueprint, Response, g, jsonify, request, send_file

from .models import HUMAN_ROLES, Study1Role
from .permissions import (
    AuthenticationError,
    Study1TokenManager,
    require_researcher_scope,
    require_study1_auth,
    require_study1_internal,
    verify_researcher_key,
)
from .privacy_routes import register_privacy_routes
from .services import (
    ActionNotAllowedInPhase,
    SqlAlchemyStudy1Repository,
    Study1Service,
    Study1ServiceError,
)

study1_bp = Blueprint("study1", __name__)
_service_override: Study1Service | None = None
register_privacy_routes(study1_bp)


def set_service_for_testing(service: Study1Service | None) -> None:
    global _service_override
    _service_override = service


def get_service() -> Study1Service:
    return _service_override or Study1Service(SqlAlchemyStudy1Repository())


def _service_error(error: Study1ServiceError):
    payload = {"error": error.code, "message": str(error)}
    if isinstance(error, ActionNotAllowedInPhase):
        payload.update(
            {
                "current_phase": error.current_phase,
                "required_phase": error.required_phase,
            }
        )
    return jsonify(payload), error.status


@study1_bp.post("/api/study1/auth/researcher")
def researcher_login():
    try:
        data = request.get_json(silent=True) or {}
        verify_researcher_key(str(data.get("key") or ""))
        return jsonify(
            {"token": Study1TokenManager().issue_researcher(data.get("scopes"))}
        ), 200
    except AuthenticationError as error:
        return jsonify({"error": error.code, "message": str(error)}), error.status


@study1_bp.post("/api/study1/task-definitions")
@require_study1_auth([Study1Role.RESEARCHER], session_argument=None)
def create_study1_task_definition():
    try:
        task = get_service().create_task_definition(
            g.study1_identity.as_actor(), request.get_json(silent=True) or {}
        )
        return jsonify(task), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.get("/api/study1/task-definitions")
@require_study1_auth([Study1Role.RESEARCHER], session_argument=None)
def list_study1_task_definitions():
    try:
        tasks = get_service().list_task_definitions(request.args.get("status"))
        return jsonify({"tasks": tasks}), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.get("/api/study1/task-definitions/<task_definition_id>")
@require_study1_auth([Study1Role.RESEARCHER], session_argument=None)
def get_study1_task_definition(task_definition_id: str):
    try:
        return jsonify(
            get_service().get_task_definition(
                task_definition_id, request.args.get("version")
            )
        ), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.put("/api/study1/task-definitions/<task_definition_id>")
@require_study1_auth([Study1Role.RESEARCHER], session_argument=None)
def replace_study1_task_definition(task_definition_id: str):
    try:
        task = get_service().replace_task_definition(
            task_definition_id,
            g.study1_identity.as_actor(),
            request.get_json(silent=True) or {},
            request.args.get("version"),
        )
        return jsonify(task), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/task-definitions/<task_definition_id>/validate")
@require_study1_auth([Study1Role.RESEARCHER], session_argument=None)
def validate_study1_task_definition(task_definition_id: str):
    try:
        task = get_service().validate_task_definition(
            task_definition_id,
            g.study1_identity.as_actor(),
            request.args.get("version"),
        )
        return jsonify(task), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions")
@require_study1_auth([Study1Role.RESEARCHER], session_argument=None)
def create_study1_session():
    try:
        data = request.get_json(silent=True) or {}
        result = get_service().create_session(
            str(data.get("session_name") or ""),
            int(data.get("invite_ttl_seconds") or 86400),
            data.get("materials_by_role") or {},
            int(data.get("minimum_review_seconds") or 0),
            data.get("experiment_config") or {},
            data.get("task_definition_id"),
        )
        return jsonify(result), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.get("/api/study1/sessions")
@require_study1_auth([Study1Role.RESEARCHER], session_argument=None)
def list_study1_sessions():
    try:
        return jsonify({"sessions": get_service().list_sessions()}), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.put("/api/study1/sessions/<session_id>/protocol-config")
@require_study1_auth([Study1Role.RESEARCHER])
def update_study1_protocol_config(session_id: str):
    try:
        result = get_service().update_protocol_config(
            session_id,
            g.study1_identity.as_actor(),
            request.get_json(silent=True) or {},
        )
        return jsonify(result), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/invites/<token>/exchange")
def exchange_study1_invite(token: str):
    try:
        return jsonify(get_service().exchange_invite(token)), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.get("/api/study1/sessions/<session_id>/me")
@require_study1_auth(HUMAN_ROLES)
def get_study1_me(session_id: str):
    snapshot = get_service().repository.get_session(session_id)
    if not snapshot:
        return jsonify({"error": "SESSION_NOT_FOUND"}), 404
    identity = g.study1_identity
    return jsonify(
        {
            "identity": identity.as_actor(),
            "session": get_service().session_dto(snapshot, identity.role.value),
        }
    )


@study1_bp.get("/api/study1/sessions/<session_id>/me/materials")
@require_study1_auth(HUMAN_ROLES)
def get_my_study1_materials(session_id: str):
    identity = g.study1_identity
    try:
        materials = get_service().get_materials(
            session_id, identity.role, enforce_phase=True
        )
        return jsonify({"materials": materials}), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/materials/<role>")
@require_study1_auth([Study1Role.RESEARCHER])
def add_study1_materials(session_id: str, role: str):
    try:
        if request.files:
            materials = get_service().add_uploaded_materials(
                session_id, role, request.files.getlist("files")
            )
        else:
            data = request.get_json(silent=True) or {}
            materials = get_service().add_materials(
                session_id, role, data.get("materials") or []
            )
        return jsonify({"materials": materials}), 201
    except (Study1ServiceError, ValueError) as error:
        if isinstance(error, Study1ServiceError):
            return _service_error(error)
        return jsonify({"error": "INVALID_MATERIAL_ROLE"}), 400


@study1_bp.post("/api/study1/sessions/<session_id>/submissions/<submission_type>")
@require_study1_auth(HUMAN_ROLES)
def create_study1_submission(session_id: str, submission_type: str):
    try:
        data = request.get_json(silent=True) or {}
        identity = g.study1_identity
        result = get_service().submit(
            session_id,
            identity.as_actor(),
            submission_type,
            str(data.get("instrument_version") or "1.0"),
            data.get("payload") or {},
            data.get("client_timestamp"),
        )
        return jsonify(_json_submission(result)), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post(
    "/api/study1/sessions/<session_id>/submissions/<submission_id>/revisions"
)
@require_study1_auth([Study1Role.RESEARCHER])
def revise_study1_submission(session_id: str, submission_id: str):
    try:
        data = request.get_json(silent=True) or {}
        result = get_service().revise_submission(
            session_id,
            submission_id,
            g.study1_identity.participant_id,
            str(data.get("reason") or ""),
            data.get("payload") or {},
            str(data.get("instrument_version") or ""),
        )
        return jsonify(_json_submission(result)), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/transition")
@require_study1_auth([Study1Role.RESEARCHER])
def transition_study1_phase(session_id: str):
    try:
        data = request.get_json(silent=True) or {}
        result = get_service().advance(
            session_id,
            g.study1_identity.as_actor(),
            str(data.get("target_phase") or ""),
            reason=data.get("reason"),
            override=bool(data.get("override", False)),
        )
        try:
            from websocket.handlers import get_socketio

            payload = {
                "session_id": session_id,
                **result["session"],
            }
            get_socketio().emit("study1_phase_updated", payload, room=session_id)
            get_socketio().emit(
                "study1_readiness_updated", payload, room=session_id
            )
        except (RuntimeError, ImportError):
            pass
        return jsonify(result), 200
    except Study1ServiceError as error:
        return _service_error(error)


def _json_submission(value):
    return {
        **value,
        "submitted_at": value["submitted_at"].isoformat().replace("+00:00", "Z"),
        "server_timestamp": value["server_timestamp"].isoformat().replace(
            "+00:00", "Z"
        ),
        "client_timestamp": (
            value["client_timestamp"].isoformat().replace("+00:00", "Z")
            if value.get("client_timestamp")
            else None
        ),
    }


def _json_domain_record(value):
    return {
        key: (
            item.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if isinstance(item, datetime)
            else item
        )
        for key, item in value.items()
    }


@study1_bp.get("/api/study1/sessions/<session_id>/me/instrument")
@require_study1_auth(HUMAN_ROLES)
def get_study1_instrument(session_id: str):
    try:
        return jsonify(
            get_service().get_current_instrument(
                session_id, g.study1_identity.as_actor()
            )
        ), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/me/instrument")
@require_study1_auth(HUMAN_ROLES)
def submit_study1_instrument(session_id: str):
    try:
        data = request.get_json(silent=True) or {}
        result = get_service().submit_instrument_response(
            session_id,
            g.study1_identity.as_actor(),
            str(data.get("instrument_definition_id") or ""),
            str(data.get("instrument_version") or ""),
            data.get("ordered_responses") or [],
        )
        return jsonify(_json_domain_record(result)), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/decisions/<decision_kind>")
@require_study1_auth(HUMAN_ROLES)
def create_study1_decision(session_id: str, decision_kind: str):
    try:
        data = request.get_json(silent=True) or {}
        result = get_service().create_individual_decision(
            session_id,
            g.study1_identity.as_actor(),
            decision_kind.replace("-", "_"),
            data.get("payload") or data,
            str(data.get("instrument_version") or "2.0"),
        )
        return jsonify(_json_domain_record(result)), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.get("/api/study1/sessions/<session_id>/shared-artifacts/<kind>")
@require_study1_auth(HUMAN_ROLES)
def get_study1_shared_artifact(session_id: str, kind: str):
    try:
        return jsonify(
            get_service().get_shared_artifact(
                session_id, g.study1_identity.as_actor(), kind.replace("-", "_")
            )
        ), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post(
    "/api/study1/sessions/<session_id>/shared-artifacts/<kind>/revisions"
)
@require_study1_auth(HUMAN_ROLES)
def create_study1_shared_revision(session_id: str, kind: str):
    try:
        data = request.get_json(silent=True) or {}
        result = get_service().create_shared_revision(
            session_id,
            g.study1_identity.as_actor(),
            kind.replace("-", "_"),
            data.get("parent_revision_id"),
            data.get("content") or {},
        )
        return jsonify(result), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post(
    "/api/study1/sessions/<session_id>/shared-artifacts/<kind>/revisions/<revision_id>/confirm"
)
@require_study1_auth(HUMAN_ROLES)
def confirm_study1_shared_revision(
    session_id: str, kind: str, revision_id: str
):
    try:
        result = get_service().confirm_shared_revision(
            session_id,
            g.study1_identity.as_actor(),
            kind.replace("-", "_"),
            revision_id,
        )
        return jsonify(result), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.get("/api/study1/sessions/<session_id>/review")
@require_study1_auth([Study1Role.PRINCIPAL])
def get_study1_review(session_id: str):
    try:
        result = get_service().get_review(
            session_id, g.study1_identity.as_actor()
        )
        return jsonify(result), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/ui-events")
@require_study1_auth(
    [Study1Role.PRINCIPAL, Study1Role.TEAMMATE_1, Study1Role.TEAMMATE_2]
)
def create_study1_ui_event(session_id: str):
    try:
        data = request.get_json(silent=True) or {}
        event = get_service().log_review_ui_event(
            session_id,
            g.study1_identity.as_actor(),
            str(data.get("event_type") or ""),
            data.get("payload") or {},
        )
        return jsonify({"event_id": event["event_id"]}), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.get("/api/study1/sessions/<session_id>/researcher")
@require_study1_auth([Study1Role.RESEARCHER])
def get_study1_researcher_dashboard(session_id: str):
    try:
        return jsonify(get_service().researcher_dashboard(session_id)), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/control/<action>")
@require_study1_auth([Study1Role.RESEARCHER])
def control_study1_session(session_id: str, action: str):
    try:
        data = request.get_json(silent=True) or {}
        result = get_service().control(
            session_id, g.study1_identity.as_actor(), action, data
        )
        _emit_control_events(session_id, action, result["session"])
        return jsonify(result), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/incidents")
@require_study1_auth([Study1Role.RESEARCHER])
def create_study1_incident(session_id: str):
    try:
        data = request.get_json(silent=True) or {}
        incident = get_service().add_incident(
            session_id,
            g.study1_identity.as_actor(),
            str(data.get("category") or "other"),
            str(data.get("severity") or "warning"),
            str(data.get("description") or ""),
            data.get("metadata") or {},
        )
        try:
            from websocket.handlers import get_socketio

            get_socketio().emit(
                "study1_incident_created",
                {
                    "session_id": session_id,
                    "incident_id": incident["incident_id"],
                    "category": incident["category"],
                    "severity": incident["severity"],
                },
                room=session_id,
            )
        except (RuntimeError, ImportError):
            pass
        return jsonify(
            {
                **incident,
                "created_at": incident["created_at"].isoformat().replace(
                    "+00:00", "Z"
                ),
            }
        ), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/clone")
@require_study1_auth([Study1Role.RESEARCHER])
def clone_study1_session(session_id: str):
    try:
        data = request.get_json(silent=True) or {}
        result = get_service().clone_session(
            session_id,
            str(data.get("session_name") or ""),
            int(data.get("invite_ttl_seconds") or 86400),
        )
        return jsonify(result), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/transcript-corrections")
@require_study1_auth([Study1Role.RESEARCHER])
def create_study1_transcript_correction(session_id: str):
    try:
        data = request.get_json(silent=True) or {}
        result = get_service().create_transcript_correction(
            session_id,
            g.study1_identity.as_actor(),
            str(data.get("segment_id") or ""),
            str(data.get("corrected_text") or ""),
            str(data.get("reason") or ""),
        )
        return jsonify(result), 201
    except Study1ServiceError as error:
        return _service_error(error)


def _emit_control_events(session_id: str, action: str, session: dict):
    try:
        from websocket.handlers import get_socketio

        event = (
            "study1_session_terminated"
            if action == "terminate"
            else "study1_phase_updated"
        )
        get_socketio().emit(
            event, {"session_id": session_id, **session}, room=session_id
        )
        get_socketio().emit(
            "study1_readiness_updated",
            {"session_id": session_id, **session},
            room=session_id,
        )
    except (RuntimeError, ImportError):
        pass


@study1_bp.post("/api/study1/sessions/<session_id>/media-commands")
@require_study1_auth([Study1Role.RESEARCHER])
def create_study1_media_command(session_id: str):
    try:
        data = request.get_json(silent=True) or {}
        result = get_service().issue_media_command(
            session_id,
            g.study1_identity.as_actor(),
            str(data.get("command") or ""),
            data.get("payload") or {},
            data.get("command_id"),
        )
        return jsonify(result), 202
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/media-access")
@require_study1_auth(HUMAN_ROLES)
def create_study1_media_access(session_id: str):
    try:
        return jsonify(
            get_service().issue_media_access(
                session_id, g.study1_identity.as_actor()
            )
        ), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/media-device")
@require_study1_auth(HUMAN_ROLES)
def report_study1_media_device(session_id: str):
    try:
        return jsonify(
            get_service().report_media_device(
                session_id,
                g.study1_identity.as_actor(),
                request.get_json(silent=True) or {},
            )
        ), 202
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.get("/api/study1/sessions/<session_id>/media-status")
@require_study1_auth([Study1Role.RESEARCHER])
def get_study1_media_status(session_id: str):
    try:
        return jsonify(get_service().media_status(session_id)), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.get(
    "/api/study1/sessions/<session_id>/recordings/<recording_id>"
)
@require_study1_auth([Study1Role.PRINCIPAL, Study1Role.RESEARCHER])
def replay_study1_recording(session_id: str, recording_id: str):
    try:
        if g.study1_identity.role is Study1Role.RESEARCHER:
            require_researcher_scope(g.study1_identity, "read_raw_media")
        upstream = get_service().get_recording(
            session_id,
            g.study1_identity.as_actor(),
            recording_id,
            request.headers.get("Range"),
        )
        headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower()
            in {"content-type", "content-range", "accept-ranges", "content-length"}
        }
        return Response(
            upstream.content,
            status=upstream.status_code,
            headers=headers,
            direct_passthrough=False,
        )
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.get("/api/study1/sessions/<session_id>/markers")
@require_study1_auth([*HUMAN_ROLES, Study1Role.RESEARCHER])
def list_study1_markers(session_id: str):
    try:
        markers = get_service().list_markers(
            session_id, g.study1_identity.as_actor()
        )
        return jsonify({"markers": [_json_domain_record(item) for item in markers]}), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/markers")
@require_study1_auth([*HUMAN_ROLES, Study1Role.RESEARCHER])
def create_study1_marker(session_id: str):
    try:
        marker = get_service().create_marker(
            session_id,
            g.study1_identity.as_actor(),
            request.get_json(silent=True) or {},
        )
        return jsonify(_json_domain_record(marker)), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.get("/api/study1/sessions/<session_id>/replay-plans")
@require_study1_auth([Study1Role.RESEARCHER])
def list_study1_replay_plans(session_id: str):
    try:
        plans = get_service().list_replay_plans(
            session_id, g.study1_identity.as_actor()
        )
        return jsonify({"replay_plans": [_json_domain_record(item) for item in plans]}), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/replay-plans")
@require_study1_auth([Study1Role.RESEARCHER])
def create_study1_replay_plan(session_id: str):
    try:
        plan = get_service().generate_replay_plan(
            session_id,
            g.study1_identity.as_actor(),
            request.get_json(silent=True) or {},
        )
        return jsonify(_json_domain_record(plan)), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/summary-actions")
@require_study1_auth([Study1Role.RESEARCHER])
def create_study1_summary_action(session_id: str):
    try:
        result = get_service().handle_summary_failure_action(
            session_id,
            g.study1_identity.as_actor(),
            request.get_json(silent=True) or {},
        )
        return jsonify(result), 202
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/summary-qa")
@require_study1_auth([Study1Role.RESEARCHER])
def create_study1_summary_qa(session_id: str):
    try:
        data = request.get_json(silent=True) or {}
        result = get_service().record_summary_qa(
            session_id,
            g.study1_identity.as_actor(),
            str(data.get("summary_artifact_id") or ""),
            data.get("ratings") or {},
        )
        return jsonify(result), 201
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/study1/sessions/<session_id>/review-events/batch")
@require_study1_auth([Study1Role.PRINCIPAL])
def create_study1_review_event_batch(session_id: str):
    try:
        data = request.get_json(silent=True) or {}
        result = get_service().record_review_event_batch(
            session_id,
            g.study1_identity.as_actor(),
            str(data.get("visit_id") or ""),
            data.get("events") or [],
        )
        return jsonify(result), 202
    except ValueError as error:
        return jsonify({"error": "INVALID_REVIEW_EVENT_BATCH", "message": str(error)}), 400
    except Study1ServiceError as error:
        return _service_error(error)
    except AuthenticationError as error:
        return jsonify({"error": error.code, "message": str(error)}), error.status


@study1_bp.post("/api/study1/sessions/<session_id>/mock-media/complete")
@require_study1_auth([Study1Role.RESEARCHER])
def complete_study1_mock_media(session_id: str):
    """Researcher-only Mock gateway completion; never starts real media."""
    try:
        snapshot = get_service().repository.get_session(session_id)
        if not snapshot:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        event_by_phase = {
            "PROXY_MEETING": "MEETING_ENDED",
            "HANDOFF": "HANDOFF_COMPLETE",
            "SYNC_MEETING": "MEETING_ENDED",
        }
        event_type = event_by_phase.get(snapshot["phase"])
        if not event_type:
            raise Study1ServiceError(
                "MOCK_COMPLETION_NOT_ALLOWED",
                "Current phase has no Mock media completion",
                409,
            )
        result = get_service().receive_media_event(
            {
                "event_id": str(uuid.uuid4()),
                "session_id": session_id,
                "phase_version": snapshot["phase_version"],
                "event_type": event_type,
                "occurred_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "payload": {"source": "researcher_mock_confirmation"},
            }
        )
        _emit_media_update(session_id, result)
        return jsonify(result), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/internal/study1/media-events")
@require_study1_internal
def receive_study1_media_event():
    try:
        result = get_service().receive_media_event(request.get_json(silent=True) or {})
        _emit_media_update(result["session"]["session_id"], result)
        return jsonify(result), 200
    except Study1ServiceError as error:
        return _service_error(error)


@study1_bp.post("/api/internal/study1/sessions/<session_id>/artifacts")
@require_study1_internal
def receive_study1_artifact(session_id: str):
    try:
        result = get_service().create_artifact(
            session_id, request.get_json(silent=True) or {}
        )
        artifact = result["artifact"]
        try:
            from websocket.handlers import get_socketio

            get_socketio().emit(
                "study1_artifact_ready",
                {
                    "session_id": session_id,
                    "artifact_id": artifact["artifact_id"],
                    "type": artifact["type"],
                    "version": artifact["version"],
                },
                room=session_id,
            )
        except (RuntimeError, ImportError):
            pass
        return (
            jsonify(
                {
                    **result,
                    "artifact": {
                        **artifact,
                        "created_at": (
                            artifact["created_at"]
                            .isoformat()
                            .replace("+00:00", "Z")
                            if hasattr(artifact["created_at"], "isoformat")
                            else artifact["created_at"]
                        ),
                    },
                }
            ),
            201 if result["created"] else 200,
        )
    except Study1ServiceError as error:
        return _service_error(error)


def _emit_media_update(session_id: str, result: dict):
    try:
        from websocket.handlers import get_socketio

        get_socketio().emit(
            "study1_readiness_updated",
            {"session_id": session_id, **result["session"]},
            room=session_id,
        )
    except (RuntimeError, ImportError):
        pass


@study1_bp.get("/api/study1/sessions/<session_id>/export")
@require_study1_auth([Study1Role.RESEARCHER])
def export_study1_session(session_id: str):
    try:
        bundle = get_service().export_bundle(session_id)
        return send_file(
            bundle,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"study1-{session_id}.zip",
            max_age=0,
        )
    except Study1ServiceError as error:
        return _service_error(error)
