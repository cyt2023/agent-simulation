"""Privacy-focused Study 1 HTTP routes."""

from __future__ import annotations

from flask import g, jsonify

from .models import Study1Role
from .permissions import (
    AuthenticationError,
    require_researcher_scope,
    require_study1_auth,
)
from .privacy_models import CONSENT_SCOPES, RESEARCHER_SCOPES


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
