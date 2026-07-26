"""Study 1 application service and persistence adapters."""

from __future__ import annotations

import hashlib
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from services.db import ResearchSessionRow, get_session_factory, is_db_configured

from .models import HUMAN_ROLES, Study1EventRow, Study1InviteRow, Study1Phase, Study1Role
from .permissions import Study1TokenManager
from .state_machine import readiness


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Study1ServiceError(ValueError):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass
class CreatedInvite:
    token: str
    invite_id: str
    session_id: str
    participant_id: str
    role: str
    expires_at: datetime

    def public_dict(self) -> dict[str, Any]:
        return {
            "invite_id": self.invite_id,
            "session_id": self.session_id,
            "participant_id": self.participant_id,
            "role": self.role,
            "expires_at": utc_iso(self.expires_at),
            "token": self.token,
            "join_path": f"/study1/join/{self.token}",
        }


class InMemoryStudy1Repository:
    """Deterministic test/development adapter with transaction-like locking."""

    def __init__(self):
        self.sessions: dict[str, dict[str, Any]] = {}
        self.invites: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def create_session(
        self, snapshot: dict[str, Any], invites: list[dict[str, Any]]
    ) -> None:
        with self._lock:
            self.sessions[snapshot["session_id"]] = snapshot
            for invite in invites:
                self.invites[invite["token_hash"]] = invite

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self.sessions.get(session_id)
            return dict(value) if value else None

    def redeem_invite(
        self, token_hash: str, used_at: datetime
    ) -> dict[str, Any] | None:
        with self._lock:
            invite = self.invites.get(token_hash)
            if invite is None:
                return None
            if invite["used_at"] is not None:
                raise Study1ServiceError(
                    "INVITE_ALREADY_USED", "Invite has already been redeemed", 409
                )
            if invite["expires_at"] <= used_at:
                raise Study1ServiceError("INVITE_EXPIRED", "Invite has expired", 410)
            invite["used_at"] = used_at
            session = self.sessions[invite["session_id"]]
            event = _role_login_event(invite, session, used_at)
            self.events.append(event)
            return dict(invite)


class SqlAlchemyStudy1Repository:
    def __init__(self):
        if not is_db_configured():
            raise Study1ServiceError(
                "DATABASE_NOT_CONFIGURED",
                "Study 1 requires a configured PostgreSQL database",
                503,
            )
        self.SessionLocal = get_session_factory()

    def create_session(
        self, snapshot: dict[str, Any], invites: list[dict[str, Any]]
    ) -> None:
        with self.SessionLocal() as db:
            db.add(
                ResearchSessionRow(
                    session_id=snapshot["session_id"],
                    session_name=snapshot["session_name"],
                    payload=snapshot,
                    updated_at=utc_now(),
                )
            )
            for item in invites:
                db.add(Study1InviteRow(**item))
            db.commit()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.SessionLocal() as db:
            row = db.scalar(
                select(ResearchSessionRow).where(
                    ResearchSessionRow.session_id == session_id
                )
            )
            if not row or row.payload.get("experiment_type") != "study1":
                return None
            return dict(row.payload)

    def redeem_invite(
        self, token_hash: str, used_at: datetime
    ) -> dict[str, Any] | None:
        with self.SessionLocal() as db:
            row = db.scalar(
                select(Study1InviteRow)
                .where(Study1InviteRow.token_hash == token_hash)
                .with_for_update()
            )
            if row is None:
                return None
            if row.used_at is not None:
                raise Study1ServiceError(
                    "INVITE_ALREADY_USED", "Invite has already been redeemed", 409
                )
            if row.expires_at <= used_at:
                raise Study1ServiceError("INVITE_EXPIRED", "Invite has expired", 410)
            row.used_at = used_at
            snapshot_row = db.scalar(
                select(ResearchSessionRow).where(
                    ResearchSessionRow.session_id == row.session_id
                )
            )
            invite = _invite_row_dict(row)
            event = _role_login_event(invite, snapshot_row.payload, used_at)
            db.add(
                Study1EventRow(
                    event_id=event["event_id"],
                    session_id=event["session_id"],
                    participant_id=event["participant_id"],
                    role=event["role"],
                    phase=event["phase"],
                    phase_version=event["phase_version"],
                    event_type=event["event_type"],
                    occurred_at=used_at,
                    payload=event["payload"],
                )
            )
            db.commit()
            return invite


def _invite_row_dict(row: Study1InviteRow) -> dict[str, Any]:
    return {
        "invite_id": row.invite_id,
        "session_id": row.session_id,
        "participant_id": row.participant_id,
        "role": row.role,
        "expires_at": row.expires_at,
        "token_hash": row.token_hash,
        "used_at": row.used_at,
        "created_at": row.created_at,
    }


def _role_login_event(
    invite: dict[str, Any], session: dict[str, Any], occurred_at: datetime
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "session_id": invite["session_id"],
        "participant_id": invite["participant_id"],
        "role": invite["role"],
        "phase": session["phase"],
        "phase_version": session["phase_version"],
        "event_type": "role_login",
        "occurred_at": utc_iso(occurred_at),
        "payload": {"invite_id": invite["invite_id"]},
    }


class Study1Service:
    def __init__(
        self,
        repository: InMemoryStudy1Repository | SqlAlchemyStudy1Repository,
        token_manager: Study1TokenManager | None = None,
    ):
        self.repository = repository
        self.tokens = token_manager or Study1TokenManager()

    def create_session(
        self, session_name: str, invite_ttl_seconds: int = 86400
    ) -> dict[str, Any]:
        clean_name = (session_name or "").strip()
        if not clean_name:
            raise Study1ServiceError(
                "SESSION_NAME_REQUIRED", "session_name is required", 400
            )
        now = utc_now()
        session_id = str(uuid.uuid4())
        participants = [
            {
                "participant_id": str(uuid.uuid4()),
                "role": role.value,
                "online": False,
            }
            for role in HUMAN_ROLES
        ]
        snapshot = {
            "session_id": session_id,
            "session_name": clean_name,
            "experiment_type": "study1",
            "status": "waiting",
            "phase": Study1Phase.SETUP.value,
            "phase_version": 1,
            "phase_started_at": utc_iso(now),
            "phase_ended_at": None,
            "entered_by": {
                "participant_id": "researcher",
                "role": Study1Role.RESEARCHER.value,
            },
            "transition_reason": "session_created",
            "prerequisites": {"satisfied": True, "missing": []},
            "completion": {},
            "phase_history": [
                {
                    "phase": Study1Phase.SETUP.value,
                    "phase_version": 1,
                    "phase_started_at": utc_iso(now),
                    "phase_ended_at": None,
                    "entered_by": {
                        "participant_id": "researcher",
                        "role": Study1Role.RESEARCHER.value,
                    },
                    "transition_reason": "session_created",
                    "prerequisites": {"satisfied": True, "missing": []},
                    "completion": {},
                }
            ],
            "participants": participants,
            "created_at": utc_iso(now),
            "protocol_version": "study1-a-1.0",
            "task_version": "1.0",
        }
        expires_at = now + timedelta(seconds=max(60, int(invite_ttl_seconds)))
        created: list[CreatedInvite] = []
        rows: list[dict[str, Any]] = []
        for participant in participants:
            raw_token = secrets.token_urlsafe(32)
            invite = CreatedInvite(
                token=raw_token,
                invite_id=str(uuid.uuid4()),
                session_id=session_id,
                participant_id=participant["participant_id"],
                role=participant["role"],
                expires_at=expires_at,
            )
            created.append(invite)
            rows.append(
                {
                    "invite_id": invite.invite_id,
                    "session_id": session_id,
                    "participant_id": invite.participant_id,
                    "role": invite.role,
                    "expires_at": expires_at,
                    "token_hash": hash_invite_token(raw_token),
                    "used_at": None,
                    "created_at": now,
                }
            )
        self.repository.create_session(snapshot, rows)
        return {
            "session": self.session_dto(snapshot),
            "invites": [invite.public_dict() for invite in created],
        }

    def exchange_invite(self, raw_token: str) -> dict[str, Any]:
        if not raw_token:
            raise Study1ServiceError("INVITE_REQUIRED", "Invite token is required", 400)
        invite = self.repository.redeem_invite(hash_invite_token(raw_token), utc_now())
        if invite is None:
            raise Study1ServiceError("INVALID_INVITE", "Invite is invalid", 404)
        token = self.tokens.issue_participant(
            invite["session_id"], invite["participant_id"], invite["role"]
        )
        session = self.repository.get_session(invite["session_id"])
        return {
            "token": token,
            "identity": {
                "session_id": invite["session_id"],
                "participant_id": invite["participant_id"],
                "role": invite["role"],
            },
            "session": self.session_dto(session, invite["role"]),
        }

    def session_dto(
        self, snapshot: dict[str, Any], role: str | None = None
    ) -> dict[str, Any]:
        base = {
            "session_id": snapshot["session_id"],
            "status": snapshot["status"],
            "phase": snapshot["phase"],
            "phase_version": snapshot["phase_version"],
            "phase_started_at": snapshot["phase_started_at"],
            **readiness(snapshot),
        }
        if role == Study1Role.PRINCIPAL.value and snapshot["phase"] == "PROXY_MEETING":
            return {
                **base,
                "waiting_room": {
                    "message": "The delegated discussion is in progress.",
                    "remaining_seconds": snapshot.get("remaining_seconds"),
                    "connection_status": "connected",
                },
            }
        return base
