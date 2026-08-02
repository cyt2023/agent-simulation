"""Privacy-focused Study 1 HTTP routes."""

from __future__ import annotations

from flask import g, jsonify, request

from .media_gateway import create_media_gateway_from_env
from .models import HUMAN_ROLES, Study1Role
from .permissions import (
    AuthenticationError,
    require_researcher_scope,
    require_study1_auth,
)
from .privacy_models import CONSENT_SCOPES, RESEARCHER_SCOPES
from .retention_service import InMemoryRetentionStore, RetentionError, RetentionService


_retention_store = InMemoryRetentionStore()
_retention_service_override: RetentionService | None = None


def set_retention_service_for_testing(service: RetentionService | None) -> None:
    global _retention_service_override
    _retention_service_override = service


def _retention_service() -> RetentionService:
    if _retention_service_override is not None:
        return _retention_service_override
    return RetentionService(
        store=_retention_store,
        media_gateway=create_media_gateway_from_env(),
    )


def register_privacy_routes(blueprint) -> None:
    @blueprint.get("/api/study1/privacy/scopes")
    @require_study1_auth([Study1Role.RESEARCHER], session_argument=None)
    def list_study1_privacy_scopes():
        try:
            require_researcher_scope(g.study1_identity, "privacy_admin")
        except AuthenticationError as error:
            return jsonify({"error": error.code, "message": str(error)}), error.status
        return jsonify(
            {
                "consent_scopes": list(CONSENT_SCOPES),
                "researcher_scopes": list(RESEARCHER_SCOPES),
            }
        ), 200

    @blueprint.post("/api/study1/sessions/<session_id>/privacy/withdrawal-requests")
    @require_study1_auth(HUMAN_ROLES)
    def request_study1_withdrawal(session_id: str):
        data = request.get_json(silent=True) or {}
        reason = str(data.get("reason") or "").strip()
        if not data.get("confirmation") or not reason:
            return jsonify(
                {
                    "error": "WITHDRAWAL_CONFIRMATION_REQUIRED",
                    "message": "A confirmed reason is required.",
                }
            ), 400
        identity = g.study1_identity
        try:
            job = _retention_service().create_dry_run(
                session_id,
                requested_by=identity.participant_id,
                subject_pseudo_ids=[identity.participant_id],
                reason_code="participant_withdrawal",
            )
            return jsonify({"accepted": True, "retention_job": job.public_dict()}), 202
        except RetentionError as error:
            return jsonify({"error": error.code, "message": str(error)}), 400

    @blueprint.post("/api/study1/privacy/retention-jobs")
    @require_study1_auth([Study1Role.RESEARCHER], session_argument=None)
    def create_study1_retention_job():
        try:
            require_researcher_scope(g.study1_identity, "privacy_admin")
            data = request.get_json(silent=True) or {}
            job = _retention_service().create_dry_run(
                str(data.get("session_id") or ""),
                requested_by=g.study1_identity.participant_id,
                subject_pseudo_ids=list(data.get("subject_pseudo_ids") or []),
                reason_code=str(data.get("reason_code") or "participant_withdrawal"),
            )
            return jsonify(job.public_dict(include_subjects=True)), 201
        except AuthenticationError as error:
            return jsonify({"error": error.code, "message": str(error)}), error.status
        except RetentionError as error:
            return jsonify({"error": error.code, "message": str(error)}), 400

    @blueprint.post("/api/study1/privacy/retention-jobs/<job_id>/execute")
    @require_study1_auth([Study1Role.RESEARCHER], session_argument=None)
    def execute_study1_retention_job(job_id: str):
        try:
            require_researcher_scope(g.study1_identity, "privacy_admin")
            data = request.get_json(silent=True) or {}
            job = _retention_service().execute(
                job_id,
                approved_manifest_checksum=str(
                    data.get("approved_manifest_checksum") or ""
                ),
                approved_by=g.study1_identity.participant_id,
                reason=str(data.get("reason") or ""),
                phase_version=int(data.get("phase_version") or 1),
            )
            return jsonify(job.public_dict()), 200
        except AuthenticationError as error:
            return jsonify({"error": error.code, "message": str(error)}), error.status
        except RetentionError as error:
            return jsonify({"error": error.code, "message": str(error)}), 400
