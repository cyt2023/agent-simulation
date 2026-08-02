"""Server-authenticated Study 1 identities and route guards."""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from functools import wraps
from typing import Any, Iterable, Mapping

from flask import g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .models import Study1Role
from .privacy_models import DEFAULT_RESEARCHER_SCOPES, RESEARCHER_SCOPES


class AuthenticationError(ValueError):
    def __init__(self, code: str, message: str, status: int = 401):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Study1Identity:
    participant_id: str
    role: Study1Role
    session_id: str | None
    kind: str
    scopes: frozenset[str] = frozenset()

    def as_actor(self) -> dict[str, str | list[str] | None]:
        return {
            "participant_id": self.participant_id,
            "role": self.role.value,
            "session_id": self.session_id,
            "scopes": sorted(self.scopes),
        }


class Study1TokenManager:
    def __init__(self, secret: str | None = None, max_age_seconds: int | None = None):
        self.secret = (
            secret
            or os.environ.get("STUDY1_TOKEN_SECRET")
            or os.environ.get("FLASK_SECRET_KEY")
            or os.environ.get("SECRET_KEY")
        )
        if not self.secret:
            raise AuthenticationError(
                "AUTH_NOT_CONFIGURED",
                "Study 1 token secret is not configured",
                503,
            )
        self.max_age_seconds = max_age_seconds or int(
            os.environ.get("STUDY1_AUTH_TOKEN_TTL_SECONDS", "43200")
        )
        self.serializer = URLSafeTimedSerializer(
            self.secret, salt="human-agent-collab-study1-v1"
        )

    def issue_participant(
        self, session_id: str, participant_id: str, role: Study1Role | str
    ) -> str:
        role_value = Study1Role(role)
        if role_value not in (
            Study1Role.PRINCIPAL,
            Study1Role.TEAMMATE_1,
            Study1Role.TEAMMATE_2,
        ):
            raise AuthenticationError("INVALID_ROLE", "Not a participant role", 403)
        return self.serializer.dumps(
            {
                "kind": "participant",
                "session_id": session_id,
                "participant_id": participant_id,
                "role": role_value.value,
            }
        )

    def issue_researcher(self, scopes: Iterable[str] | None = None) -> str:
        clean_scopes = _normalize_researcher_scopes(scopes)
        return self.serializer.dumps(
            {
                "kind": "researcher",
                "session_id": None,
                "participant_id": "researcher",
                "role": Study1Role.RESEARCHER.value,
                "scopes": sorted(clean_scopes),
            }
        )

    def verify(self, token: str) -> Study1Identity:
        try:
            payload = self.serializer.loads(token, max_age=self.max_age_seconds)
            role = Study1Role(payload["role"])
            kind = str(payload["kind"])
            if kind == "participant" and role not in (
                Study1Role.PRINCIPAL,
                Study1Role.TEAMMATE_1,
                Study1Role.TEAMMATE_2,
            ):
                raise ValueError("invalid participant role")
            if kind == "researcher" and role is not Study1Role.RESEARCHER:
                raise ValueError("invalid researcher role")
            scopes = frozenset(
                _normalize_researcher_scopes(payload.get("scopes"))
                if kind == "researcher"
                else set()
            )
            return Study1Identity(
                participant_id=str(payload["participant_id"]),
                role=role,
                session_id=payload.get("session_id"),
                kind=kind,
                scopes=scopes,
            )
        except SignatureExpired as error:
            raise AuthenticationError("AUTH_TOKEN_EXPIRED", "Token expired") from error
        except (BadSignature, KeyError, TypeError, ValueError) as error:
            raise AuthenticationError("INVALID_AUTH_TOKEN", "Invalid token") from error


def verify_researcher_key(provided: str) -> None:
    configured = os.environ.get("STUDY1_RESEARCHER_KEY", "")
    if not configured:
        raise AuthenticationError(
            "RESEARCHER_AUTH_NOT_CONFIGURED",
            "Study 1 researcher authentication is not configured",
            503,
        )
    if not hmac.compare_digest(configured, provided or ""):
        raise AuthenticationError("INVALID_RESEARCHER_KEY", "Invalid researcher key")


def verify_internal_key(provided: str) -> None:
    configured = os.environ.get("STUDY1_INTERNAL_API_KEY", "")
    if not configured:
        raise AuthenticationError(
            "INTERNAL_AUTH_NOT_CONFIGURED",
            "Study 1 internal API authentication is not configured",
            503,
        )
    if not hmac.compare_digest(configured, provided or ""):
        raise AuthenticationError("INVALID_INTERNAL_API_KEY", "Invalid internal API key")


def _normalize_researcher_scopes(scopes: Iterable[str] | None) -> frozenset[str]:
    if scopes is None:
        return DEFAULT_RESEARCHER_SCOPES
    allowed = set(RESEARCHER_SCOPES)
    clean = {str(scope) for scope in scopes if str(scope) in allowed}
    return frozenset(clean)


def require_researcher_scope(identity: Study1Identity, scope: str) -> None:
    if identity.kind != "researcher" or identity.role is not Study1Role.RESEARCHER:
        raise AuthenticationError("FORBIDDEN", "Researcher role required", 403)
    if scope not in identity.scopes:
        raise AuthenticationError(
            "RESEARCHER_SCOPE_REQUIRED",
            f"Researcher scope required: {scope}",
            403,
        )


def study2_data_available(
    identity: Study1Identity | Mapping[str, Any],
    session: Mapping[str, Any],
    resource: str,
) -> bool:
    """Keep principal isolation enforceable outside the HTTP presentation layer."""

    role = (
        identity.role.value
        if isinstance(identity, Study1Identity)
        else getattr(identity.get("role"), "value", identity.get("role"))
    )
    return not (
        resource == "utterances"
        and role == Study1Role.PRINCIPAL.value
        and session.get("phase") == "PROXY_MEETING"
    )


def require_study1_internal(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            provided = request.headers.get("X-Study1-Internal-Key", "")
            verify_internal_key(provided)
            return function(*args, **kwargs)
        except AuthenticationError as error:
            return (
                jsonify({"error": error.code, "message": str(error)}),
                error.status,
            )

    return wrapped


def bearer_token_from_request() -> str:
    value = request.headers.get("Authorization", "")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("AUTH_REQUIRED", "Bearer token required")
    return token.strip()


def require_study1_auth(
    roles: Iterable[Study1Role | str] | None = None,
    session_argument: str | None = "session_id",
):
    allowed = {Study1Role(role) for role in roles} if roles else None

    def decorator(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            try:
                identity = Study1TokenManager().verify(bearer_token_from_request())
                if allowed is not None and identity.role not in allowed:
                    raise AuthenticationError(
                        "FORBIDDEN", "Role is not allowed for this action", 403
                    )
                requested_session = (
                    kwargs.get(session_argument) if session_argument else None
                )
                if (
                    requested_session
                    and identity.kind == "participant"
                    and identity.session_id != requested_session
                ):
                    raise AuthenticationError(
                        "SESSION_MISMATCH",
                        "Token does not belong to this session",
                        403,
                    )
                g.study1_identity = identity
                return function(*args, **kwargs)
            except AuthenticationError as error:
                return (
                    jsonify({"error": error.code, "message": str(error)}),
                    error.status,
                )

        return wrapped

    return decorator
