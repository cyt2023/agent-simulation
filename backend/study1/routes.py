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
    return jsonify({"error": error.code, "message": str(error)}), error.status


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
