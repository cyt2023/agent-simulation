"""HTTP endpoints for the versioned, read-only Study 2 contract."""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from .models import HUMAN_ROLES, Study1Role
from .permissions import require_study1_auth
from .services import Study1ServiceError
from .study2_contracts import contract_etag
from .study2_service import Study2ReadOnlyService


study2_bp = Blueprint("study2", __name__)
_service_override: Study2ReadOnlyService | None = None


def set_study2_service_for_testing(service: Study2ReadOnlyService | None) -> None:
    global _service_override
    _service_override = service


def get_study2_service() -> Study2ReadOnlyService:
    if _service_override is not None:
        return _service_override
    from .routes import get_service

    return Study2ReadOnlyService(get_service())


def _error(error: Study1ServiceError):
    return jsonify({"error": error.code, "message": str(error)}), error.status


def _read(session_id: str, resource: str):
    try:
        payload = get_study2_service().read_resource(
            session_id,
            g.study1_identity.as_actor(),
            resource,
            cursor=request.args.get("cursor"),
            limit=request.args.get("limit"),
        )
        etag = contract_etag(payload)
        if request.if_none_match.contains(etag):
            response = Response(status=304)
            response.set_etag(etag)
            return response
        response = jsonify(payload)
        response.set_etag(etag)
        return response, 200
    except Study1ServiceError as error:
        return _error(error)


@study2_bp.get("/api/study2/v1/sessions/<session_id>/utterances")
@require_study1_auth((*HUMAN_ROLES, Study1Role.RESEARCHER))
def read_study2_utterances(session_id: str):
    return _read(session_id, "utterances")


@study2_bp.get("/api/study2/v1/sessions/<session_id>/decisions")
@require_study1_auth((*HUMAN_ROLES, Study1Role.RESEARCHER))
def read_study2_decisions(session_id: str):
    return _read(session_id, "decisions")


@study2_bp.get("/api/study2/v1/sessions/<session_id>/facts")
@require_study1_auth((*HUMAN_ROLES, Study1Role.RESEARCHER))
def read_study2_facts(session_id: str):
    return _read(session_id, "facts")


@study2_bp.get("/api/study2/v1/sessions/<session_id>/proxy-authority")
@require_study1_auth((*HUMAN_ROLES, Study1Role.RESEARCHER))
def read_study2_proxy_authority(session_id: str):
    return _read(session_id, "proxy-authority")


@study2_bp.get("/api/study2/v1/sessions/<session_id>/baseline-recap")
@require_study1_auth((*HUMAN_ROLES, Study1Role.RESEARCHER))
def read_study2_baseline_recap(session_id: str):
    return _read(session_id, "baseline-recap")


@study2_bp.get("/api/study2/v1/sessions/<session_id>/features")
@require_study1_auth((*HUMAN_ROLES, Study1Role.RESEARCHER))
def read_study2_features(session_id: str):
    return _read(session_id, "features")


@study2_bp.get("/api/study2/v1/sessions/<session_id>/module-telemetry")
@require_study1_auth((*HUMAN_ROLES, Study1Role.RESEARCHER))
def read_study2_module_telemetry(session_id: str):
    return _read(session_id, "module-telemetry")
