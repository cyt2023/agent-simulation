"""HTTP boundary for Study 1 only."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from flask import Blueprint, Response, g, jsonify, request, send_file

from .models import HUMAN_ROLES, Study1Role
from .permissions import (
    AuthenticationError,
    Study1TokenManager,
    require_study1_auth,
    require_study1_internal,
    verify_researcher_key,
)
from .services import (
    ActionNotAllowedInPhase,
    SqlAlchemyStudy1Repository,
    Study1Service,
    Study1ServiceError,
)

study1_bp = Blueprint("study1", __name__)
_service_override: Study1Service | None = None


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
        return jsonify({"token": Study1TokenManager().issue_researcher()}), 200
    except AuthenticationError as error:
        return jsonify({"error": error.code, "message": str(error)}), error.status


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
        materials = get_service().get_materials(session_id, identity.role)
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
@require_study1_auth([Study1Role.PRINCIPAL])
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
@require_study1_auth([Study1Role.PRINCIPAL])
def replay_study1_recording(session_id: str, recording_id: str):
    try:
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
