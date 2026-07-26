"""HTTP boundary for Study 1 only."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from .models import HUMAN_ROLES, Study1Role
from .permissions import (
    AuthenticationError,
    Study1TokenManager,
    require_study1_auth,
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
        )
        return jsonify(result), 201
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
        except RuntimeError:
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
