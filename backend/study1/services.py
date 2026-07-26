"""Study 1 application service and persistence adapters."""

from __future__ import annotations

import hashlib
import copy
import io
import json
import os
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from services.db import ResearchSessionRow, get_session_factory, is_db_configured

from .models import (
    HUMAN_ROLES,
    Study1EventRow,
    Study1ArtifactRow,
    Study1InviteRow,
    Study1IncidentRow,
    Study1MaterialRow,
    Study1Phase,
    Study1Role,
    Study1SubmissionRow,
)
from .media_gateway import COMMANDS, EVENT_TYPES, MediaGateway, MockMediaGateway
from .permissions import Study1TokenManager
from .state_machine import (
    InvalidTransition,
    OverrideReasonRequired,
    PrerequisitesNotMet,
    readiness,
    transition_phase,
)


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


class ActionNotAllowedInPhase(Study1ServiceError):
    def __init__(self, current_phase: str, required_phase: str):
        super().__init__(
            "ACTION_NOT_ALLOWED_IN_PHASE",
            f"Action requires {required_phase}, current phase is {current_phase}",
            409,
        )
        self.current_phase = current_phase
        self.required_phase = required_phase


SUBMISSION_RULES: dict[str, tuple[Study1Phase, tuple[Study1Role, ...]]] = {
    "material_ack": (Study1Phase.MATERIAL_READING, HUMAN_ROLES),
    "pre_vote": (Study1Phase.PRE_VOTE, HUMAN_ROLES),
    "proxy_config": (Study1Phase.PROXY_CONFIGURATION, (Study1Role.PRINCIPAL,)),
    "proxy_ready": (
        Study1Phase.PROXY_CONFIGURATION,
        (Study1Role.TEAMMATE_1, Study1Role.TEAMMATE_2),
    ),
    "tentative_decision": (
        Study1Phase.TENTATIVE_DECISION,
        (Study1Role.TEAMMATE_1, Study1Role.TEAMMATE_2),
    ),
    "delegation_expectation": (
        Study1Phase.DELEGATION_EXPECTATION,
        (Study1Role.PRINCIPAL,),
    ),
    "comprehension_measurement": (
        Study1Phase.COMPREHENSION_MEASUREMENT,
        (Study1Role.PRINCIPAL,),
    ),
    "final_decision": (Study1Phase.FINAL_DECISION, HUMAN_ROLES),
    "followup_task": (Study1Phase.FOLLOWUP_TASK, HUMAN_ROLES),
    "post_survey": (Study1Phase.POST_SURVEY, HUMAN_ROLES),
}

REVIEW_UI_EVENTS = {
    "review_page_enter",
    "review_page_leave",
    "summary_visible",
    "transcript_expand",
    "transcript_collapse",
    "transcript_segment_view",
    "scroll_depth",
    "active_reading_time",
}


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
        self.materials: list[dict[str, Any]] = []
        self.submissions: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []
        self.incidents: list[dict[str, Any]] = []
        self.idempotency_keys: set[str] = set()
        self._lock = threading.RLock()

    def create_session(
        self,
        snapshot: dict[str, Any],
        invites: list[dict[str, Any]],
        materials: list[dict[str, Any]] | None = None,
    ) -> None:
        with self._lock:
            self.sessions[snapshot["session_id"]] = snapshot
            for invite in invites:
                self.invites[invite["token_hash"]] = invite
            self.materials.extend(copy.deepcopy(materials or []))

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self.sessions.get(session_id)
            return copy.deepcopy(value) if value else None

    def list_materials(self, session_id: str, role: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                copy.deepcopy(item)
                for item in self.materials
                if item["session_id"] == session_id and item["role"] == role
            ]

    def add_materials(self, materials: list[dict[str, Any]]) -> None:
        with self._lock:
            self.materials.extend(copy.deepcopy(materials))

    def transition(
        self,
        session_id: str,
        target_phase: str,
        actor: dict[str, Any],
        reason: str | None,
        override: bool,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            transition = transition_phase(
                session, target_phase, actor, reason=reason, override=override
            )
            if session["phase"] == Study1Phase.COMPLETED.value:
                session["status"] = "completed"
            events = _transition_events(session_id, actor, transition)
            self.events.extend(copy.deepcopy(events))
            return copy.deepcopy(session), events

    def create_submission(
        self,
        session_id: str,
        identity: dict[str, Any],
        submission_type: str,
        instrument_version: str,
        payload: dict[str, Any],
        client_timestamp: datetime | None,
    ) -> dict[str, Any]:
        with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            row = _build_submission(
                session,
                identity,
                submission_type,
                instrument_version,
                payload,
                client_timestamp,
                self.submissions,
            )
            self.submissions.append(copy.deepcopy(row))
            session["completion"][
                f"{submission_type}:{identity['role']}"
            ] = True
            event = _submission_event(session, row)
            self.events.append(event)
            return copy.deepcopy(row)

    def create_revision(
        self,
        session_id: str,
        submission_id: str,
        operator: str,
        reason: str,
        payload: dict[str, Any],
        instrument_version: str,
    ) -> dict[str, Any]:
        with self._lock:
            original = next(
                (
                    item
                    for item in self.submissions
                    if item["session_id"] == session_id
                    and item["submission_id"] == submission_id
                ),
                None,
            )
            if original is None:
                raise Study1ServiceError(
                    "SUBMISSION_NOT_FOUND", "Submission not found", 404
                )
            revision = _revision_from(
                original, operator, reason, payload, instrument_version
            )
            self.submissions.append(revision)
            return copy.deepcopy(revision)

    def add_artifact_for_testing(self, artifact: dict[str, Any]) -> None:
        with self._lock:
            self.artifacts.append(copy.deepcopy(artifact))

    def open_review(
        self, session_id: str, identity: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            session = self.sessions.get(session_id)
            _validate_review_access(session, identity)
            now = utc_now()
            if not session.get("review_opened_at"):
                session["review_opened_at"] = utc_iso(now)
            session["completion"]["review_opened:principal"] = True
            event = _ui_event(session, identity, "review_page_enter", {}, now)
            self.events.append(event)
            artifacts = [
                copy.deepcopy(item)
                for item in self.artifacts
                if item["session_id"] == session_id
                and item["type"] in ("summary", "transcript")
            ]
            return _review_payload(artifacts)

    def record_ui_event(
        self,
        session_id: str,
        identity: dict[str, Any],
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            session = self.sessions.get(session_id)
            _validate_review_access(session, identity)
            event = _record_review_ui_event(
                session, identity, event_type, payload, utc_now()
            )
            self.events.append(event)
            return copy.deepcopy(event)

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(value) for value in self.sessions.values()]

    def control_session(
        self,
        session_id: str,
        action: str,
        actor: dict[str, Any],
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            events = _apply_session_control(session, action, actor, payload)
            self.events.extend(copy.deepcopy(events))
            return copy.deepcopy(session), events

    def add_incident(
        self,
        session_id: str,
        actor: dict[str, Any],
        category: str,
        severity: str,
        description: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            incident = _new_incident(
                session_id, actor, category, severity, description, metadata
            )
            self.incidents.append(copy.deepcopy(incident))
            self.events.append(_incident_event(session, actor, incident))
            return incident

    def participant_status(
        self, session_id: str, identity: dict[str, Any], online: bool
    ) -> None:
        with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                return
            for participant in session["participants"]:
                if participant["participant_id"] == identity["participant_id"]:
                    participant["online"] = bool(online)
                    break
            self.events.append(
                _participant_status_event(session, identity, bool(online))
            )

    def dashboard(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            return _dashboard_payload(
                copy.deepcopy(session),
                [a for a in self.artifacts if a["session_id"] == session_id],
                [i for i in self.incidents if i["session_id"] == session_id],
            )

    def export_data(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            return {
                "session": copy.deepcopy(session),
                "events": copy.deepcopy(
                    [item for item in self.events if item["session_id"] == session_id]
                ),
                "submissions": copy.deepcopy(
                    [item for item in self.submissions if item["session_id"] == session_id]
                ),
                "artifacts": copy.deepcopy(
                    [item for item in self.artifacts if item["session_id"] == session_id]
                ),
                "incidents": copy.deepcopy(
                    [item for item in self.incidents if item["session_id"] == session_id]
                ),
                "materials": copy.deepcopy(
                    [item for item in self.materials if item["session_id"] == session_id]
                ),
            }

    def record_media_command(
        self, session_id: str, envelope: dict[str, Any]
    ) -> bool:
        with self._lock:
            key = f"media-command:{envelope['command_id']}"
            if key in self.idempotency_keys:
                return False
            session = self.sessions.get(session_id)
            if not session:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            self.idempotency_keys.add(key)
            self.events.append(_media_command_event(session, envelope, key))
            return True

    def record_media_event(
        self, envelope: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            key = f"media-event:{envelope['event_id']}"
            session = self.sessions.get(envelope["session_id"])
            if not session:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            if key in self.idempotency_keys:
                return False, copy.deepcopy(session)
            _apply_media_event(session, envelope)
            self.idempotency_keys.add(key)
            self.events.append(_media_event_log(session, envelope, key))
            return True, copy.deepcopy(session)

    def create_artifact(
        self, session_id: str, artifact: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            if any(item["artifact_id"] == artifact["artifact_id"] for item in self.artifacts):
                existing = next(
                    item for item in self.artifacts if item["artifact_id"] == artifact["artifact_id"]
                )
                return False, copy.deepcopy(existing)
            self.artifacts.append(copy.deepcopy(artifact))
            if artifact["type"] == "summary":
                session["completion"]["summary_artifact_ready"] = True
            self.events.append(_artifact_ready_event(session, artifact))
            return True, copy.deepcopy(artifact)

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
        self,
        snapshot: dict[str, Any],
        invites: list[dict[str, Any]],
        materials: list[dict[str, Any]] | None = None,
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
            for item in materials or []:
                db.add(Study1MaterialRow(**item))
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

    def list_materials(self, session_id: str, role: str) -> list[dict[str, Any]]:
        with self.SessionLocal() as db:
            rows = db.scalars(
                select(Study1MaterialRow)
                .where(
                    Study1MaterialRow.session_id == session_id,
                    Study1MaterialRow.role == role,
                )
                .order_by(Study1MaterialRow.id.asc())
            ).all()
            return [_material_row_dict(row) for row in rows]

    def add_materials(self, materials: list[dict[str, Any]]) -> None:
        with self.SessionLocal() as db:
            for item in materials:
                db.add(Study1MaterialRow(**item))
            db.commit()

    def transition(
        self,
        session_id: str,
        target_phase: str,
        actor: dict[str, Any],
        reason: str | None,
        override: bool,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with self.SessionLocal() as db:
            row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if not row or row.payload.get("experiment_type") != "study1":
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            snapshot = copy.deepcopy(row.payload)
            transition = transition_phase(
                snapshot, target_phase, actor, reason=reason, override=override
            )
            if snapshot["phase"] == Study1Phase.COMPLETED.value:
                snapshot["status"] = "completed"
            events = _transition_events(session_id, actor, transition)
            for event in events:
                db.add(_event_orm(event))
            row.payload = snapshot
            row.updated_at = utc_now()
            db.commit()
            return snapshot, events

    def create_submission(
        self,
        session_id: str,
        identity: dict[str, Any],
        submission_type: str,
        instrument_version: str,
        payload: dict[str, Any],
        client_timestamp: datetime | None,
    ) -> dict[str, Any]:
        with self.SessionLocal() as db:
            snapshot_row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if not snapshot_row or snapshot_row.payload.get("experiment_type") != "study1":
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            existing_rows = db.scalars(
                select(Study1SubmissionRow).where(
                    Study1SubmissionRow.session_id == session_id,
                    Study1SubmissionRow.participant_id == identity["participant_id"],
                    Study1SubmissionRow.previous_submission_id.is_(None),
                )
            ).all()
            existing = [_submission_row_dict(item) for item in existing_rows]
            snapshot = copy.deepcopy(snapshot_row.payload)
            value = _build_submission(
                snapshot,
                identity,
                submission_type,
                instrument_version,
                payload,
                client_timestamp,
                existing,
            )
            db.add(Study1SubmissionRow(**_submission_orm_fields(value)))
            snapshot["completion"][f"{submission_type}:{identity['role']}"] = True
            event = _submission_event(snapshot, value)
            db.add(_event_orm(event))
            snapshot_row.payload = snapshot
            snapshot_row.updated_at = utc_now()
            db.commit()
            return value

    def create_revision(
        self,
        session_id: str,
        submission_id: str,
        operator: str,
        reason: str,
        payload: dict[str, Any],
        instrument_version: str,
    ) -> dict[str, Any]:
        with self.SessionLocal() as db:
            original_row = db.scalar(
                select(Study1SubmissionRow).where(
                    Study1SubmissionRow.session_id == session_id,
                    Study1SubmissionRow.submission_id == submission_id,
                )
            )
            if original_row is None:
                raise Study1ServiceError(
                    "SUBMISSION_NOT_FOUND", "Submission not found", 404
                )
            revision = _revision_from(
                _submission_row_dict(original_row),
                operator,
                reason,
                payload,
                instrument_version,
            )
            db.add(Study1SubmissionRow(**_submission_orm_fields(revision)))
            db.commit()
            return revision

    def open_review(
        self, session_id: str, identity: dict[str, Any]
    ) -> dict[str, Any]:
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if not session_row:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            snapshot = copy.deepcopy(session_row.payload)
            _validate_review_access(snapshot, identity)
            now = utc_now()
            if not snapshot.get("review_opened_at"):
                snapshot["review_opened_at"] = utc_iso(now)
            snapshot["completion"]["review_opened:principal"] = True
            event = _ui_event(snapshot, identity, "review_page_enter", {}, now)
            db.add(_event_orm(event))
            session_row.payload = snapshot
            session_row.updated_at = now
            artifact_rows = db.scalars(
                select(Study1ArtifactRow)
                .where(
                    Study1ArtifactRow.session_id == session_id,
                    Study1ArtifactRow.type.in_(("summary", "transcript")),
                )
                .order_by(Study1ArtifactRow.created_at.asc())
            ).all()
            artifacts = [_artifact_row_dict(item) for item in artifact_rows]
            db.commit()
            return _review_payload(artifacts)

    def record_ui_event(
        self,
        session_id: str,
        identity: dict[str, Any],
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if not session_row:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            snapshot = copy.deepcopy(session_row.payload)
            _validate_review_access(snapshot, identity)
            event = _record_review_ui_event(
                snapshot, identity, event_type, payload, utc_now()
            )
            db.add(_event_orm(event))
            session_row.payload = snapshot
            session_row.updated_at = utc_now()
            db.commit()
            return event

    def list_sessions(self) -> list[dict[str, Any]]:
        with self.SessionLocal() as db:
            rows = db.scalars(select(ResearchSessionRow)).all()
            return [
                dict(row.payload)
                for row in rows
                if row.payload and row.payload.get("experiment_type") == "study1"
            ]

    def control_session(
        self,
        session_id: str,
        action: str,
        actor: dict[str, Any],
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with self.SessionLocal() as db:
            row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if not row or row.payload.get("experiment_type") != "study1":
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            snapshot = copy.deepcopy(row.payload)
            events = _apply_session_control(snapshot, action, actor, payload)
            for event in events:
                db.add(_event_orm(event))
            row.payload = snapshot
            row.updated_at = utc_now()
            db.commit()
            return snapshot, events

    def add_incident(
        self,
        session_id: str,
        actor: dict[str, Any],
        category: str,
        severity: str,
        description: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow).where(
                    ResearchSessionRow.session_id == session_id
                )
            )
            if not session_row:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            incident = _new_incident(
                session_id, actor, category, severity, description, metadata
            )
            db.add(
                Study1IncidentRow(
                    incident_id=incident["incident_id"],
                    session_id=session_id,
                    category=incident["category"],
                    severity=incident["severity"],
                    description=incident["description"],
                    created_at=incident["created_at"],
                    created_by=incident["created_by"],
                    metadata_payload=incident["metadata"],
                )
            )
            db.add(
                _event_orm(
                    _incident_event(session_row.payload, actor, incident)
                )
            )
            db.commit()
            return incident

    def participant_status(
        self, session_id: str, identity: dict[str, Any], online: bool
    ) -> None:
        with self.SessionLocal() as db:
            row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if not row or row.payload.get("experiment_type") != "study1":
                return
            snapshot = copy.deepcopy(row.payload)
            for participant in snapshot["participants"]:
                if participant["participant_id"] == identity["participant_id"]:
                    participant["online"] = bool(online)
                    break
            db.add(_event_orm(_participant_status_event(snapshot, identity, online)))
            row.payload = snapshot
            row.updated_at = utc_now()
            db.commit()

    def dashboard(self, session_id: str) -> dict[str, Any]:
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow).where(
                    ResearchSessionRow.session_id == session_id
                )
            )
            if not session_row or session_row.payload.get("experiment_type") != "study1":
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            artifacts = db.scalars(
                select(Study1ArtifactRow).where(
                    Study1ArtifactRow.session_id == session_id
                )
            ).all()
            incidents = db.scalars(
                select(Study1IncidentRow).where(
                    Study1IncidentRow.session_id == session_id
                )
            ).all()
            return _dashboard_payload(
                dict(session_row.payload),
                [_artifact_row_dict(item) for item in artifacts],
                [
                    {
                        "incident_id": item.incident_id,
                        "session_id": item.session_id,
                    }
                    for item in incidents
                ],
            )

    def export_data(self, session_id: str) -> dict[str, Any]:
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow).where(
                    ResearchSessionRow.session_id == session_id
                )
            )
            if not session_row or session_row.payload.get("experiment_type") != "study1":
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            event_rows = db.scalars(
                select(Study1EventRow)
                .where(Study1EventRow.session_id == session_id)
                .order_by(Study1EventRow.occurred_at.asc())
            ).all()
            submission_rows = db.scalars(
                select(Study1SubmissionRow)
                .where(Study1SubmissionRow.session_id == session_id)
                .order_by(Study1SubmissionRow.server_timestamp.asc())
            ).all()
            artifact_rows = db.scalars(
                select(Study1ArtifactRow)
                .where(Study1ArtifactRow.session_id == session_id)
                .order_by(Study1ArtifactRow.created_at.asc())
            ).all()
            incident_rows = db.scalars(
                select(Study1IncidentRow)
                .where(Study1IncidentRow.session_id == session_id)
                .order_by(Study1IncidentRow.created_at.asc())
            ).all()
            material_rows = db.scalars(
                select(Study1MaterialRow)
                .where(Study1MaterialRow.session_id == session_id)
                .order_by(Study1MaterialRow.id.asc())
            ).all()
            return {
                "session": dict(session_row.payload),
                "events": [
                    {
                        "event_id": row.event_id,
                        "session_id": row.session_id,
                        "participant_id": row.participant_id,
                        "role": row.role,
                        "phase": row.phase,
                        "phase_version": row.phase_version,
                        "event_type": row.event_type,
                        "occurred_at": row.occurred_at,
                        "payload": dict(row.payload or {}),
                        "idempotency_key": row.idempotency_key,
                    }
                    for row in event_rows
                ],
                "submissions": [_submission_row_dict(row) for row in submission_rows],
                "artifacts": [_artifact_row_dict(row) for row in artifact_rows],
                "incidents": [
                    {
                        "incident_id": row.incident_id,
                        "session_id": row.session_id,
                        "category": row.category,
                        "severity": row.severity,
                        "description": row.description,
                        "created_at": row.created_at,
                        "created_by": row.created_by,
                        "metadata": dict(row.metadata_payload or {}),
                    }
                    for row in incident_rows
                ],
                "materials": [_material_row_dict(row) for row in material_rows],
            }

    def record_media_command(
        self, session_id: str, envelope: dict[str, Any]
    ) -> bool:
        key = f"media-command:{envelope['command_id']}"
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if not session_row:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            existing = db.scalar(
                select(Study1EventRow).where(
                    Study1EventRow.idempotency_key == key
                )
            )
            if existing:
                return False
            db.add(_event_orm(_media_command_event(session_row.payload, envelope, key)))
            db.commit()
            return True

    def record_media_event(
        self, envelope: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        key = f"media-event:{envelope['event_id']}"
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == envelope["session_id"])
                .with_for_update()
            )
            if not session_row:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            existing = db.scalar(
                select(Study1EventRow).where(
                    Study1EventRow.idempotency_key == key
                )
            )
            if existing:
                return False, dict(session_row.payload)
            snapshot = copy.deepcopy(session_row.payload)
            _apply_media_event(snapshot, envelope)
            db.add(_event_orm(_media_event_log(snapshot, envelope, key)))
            session_row.payload = snapshot
            session_row.updated_at = utc_now()
            db.commit()
            return True, snapshot

    def create_artifact(
        self, session_id: str, artifact: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if not session_row:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            existing = db.scalar(
                select(Study1ArtifactRow).where(
                    Study1ArtifactRow.artifact_id == artifact["artifact_id"]
                )
            )
            if existing:
                return False, _artifact_row_dict(existing)
            db.add(
                Study1ArtifactRow(
                    artifact_id=artifact["artifact_id"],
                    session_id=session_id,
                    type=artifact["type"],
                    version=artifact["version"],
                    content=artifact.get("content"),
                    storage_uri=artifact.get("storage_uri"),
                    checksum=artifact["checksum"],
                    created_at=artifact["created_at"],
                    generator_version=artifact["generator_version"],
                    artifact_metadata=artifact["metadata"],
                )
            )
            snapshot = copy.deepcopy(session_row.payload)
            if artifact["type"] == "summary":
                snapshot["completion"]["summary_artifact_ready"] = True
            db.add(_event_orm(_artifact_ready_event(snapshot, artifact)))
            session_row.payload = snapshot
            session_row.updated_at = utc_now()
            db.commit()
            return True, artifact

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


def _material_row_dict(row: Study1MaterialRow) -> dict[str, Any]:
    return {
        "material_id": row.material_id,
        "session_id": row.session_id,
        "role": row.role,
        "title": row.title,
        "content": row.content,
        "storage_uri": row.storage_uri,
        "checksum": row.checksum,
        "created_at": utc_iso(row.created_at),
        "metadata": dict(row.metadata_payload or {}),
    }


def _submission_row_dict(row: Study1SubmissionRow) -> dict[str, Any]:
    return {
        "submission_id": row.submission_id,
        "session_id": row.session_id,
        "participant_id": row.participant_id,
        "role": row.role,
        "submission_type": (row.payload or {}).get("_submission_type"),
        "phase": row.phase,
        "instrument_version": row.instrument_version,
        "payload": {
            key: value
            for key, value in (row.payload or {}).items()
            if key != "_submission_type"
        },
        "submitted_at": row.submitted_at,
        "server_timestamp": row.server_timestamp,
        "client_timestamp": row.client_timestamp,
        "locked": row.locked,
        "previous_submission_id": row.previous_submission_id,
        "revision_operator": row.revision_operator,
        "revision_reason": row.revision_reason,
    }


def _artifact_row_dict(row: Study1ArtifactRow) -> dict[str, Any]:
    return {
        "artifact_id": row.artifact_id,
        "session_id": row.session_id,
        "type": row.type,
        "version": row.version,
        "content": row.content,
        "storage_uri": row.storage_uri,
        "checksum": row.checksum,
        "created_at": utc_iso(row.created_at),
        "generator_version": row.generator_version,
        "metadata": dict(row.artifact_metadata or {}),
    }


def _submission_orm_fields(value: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(value["payload"])
    payload["_submission_type"] = value["submission_type"]
    return {
        "submission_id": value["submission_id"],
        "session_id": value["session_id"],
        "participant_id": value["participant_id"],
        "role": value["role"],
        "phase": value["phase"],
        "instrument_version": value["instrument_version"],
        "payload": payload,
        "submitted_at": value["submitted_at"],
        "server_timestamp": value["server_timestamp"],
        "client_timestamp": value["client_timestamp"],
        "locked": value["locked"],
        "previous_submission_id": value.get("previous_submission_id"),
        "revision_operator": value.get("revision_operator"),
        "revision_reason": value.get("revision_reason"),
    }


def _event_orm(event: dict[str, Any]) -> Study1EventRow:
    occurred = event.get("occurred_at")
    if isinstance(occurred, str):
        occurred = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
    return Study1EventRow(
        event_id=event["event_id"],
        session_id=event["session_id"],
        participant_id=event.get("participant_id"),
        role=event.get("role"),
        phase=event["phase"],
        phase_version=event["phase_version"],
        event_type=event["event_type"],
        occurred_at=occurred or utc_now(),
        payload=event.get("payload") or {},
        idempotency_key=event.get("idempotency_key"),
    )


def _transition_events(
    session_id: str, actor: dict[str, Any], transition: dict[str, Any]
) -> list[dict[str, Any]]:
    common = {
        "session_id": session_id,
        "participant_id": actor.get("participant_id"),
        "role": actor.get("role"),
        "phase": transition["to_phase"],
        "phase_version": transition["phase_version"],
        "occurred_at": transition["occurred_at"],
    }
    events = []
    if transition["override"]:
        events.append(
            {
                **common,
                "event_id": str(uuid.uuid4()),
                "event_type": "override",
                "payload": {
                    "from_phase": transition["from_phase"],
                    "target_phase": transition["to_phase"],
                    "reason": transition["transition_reason"],
                    "missing_prerequisites": transition["prerequisites"]["missing"],
                },
            }
        )
    events.append(
        {
            **common,
            "event_id": str(uuid.uuid4()),
            "event_type": "phase_transition",
            "payload": transition,
        }
    )
    return events


def _build_submission(
    session: dict[str, Any],
    identity: dict[str, Any],
    submission_type: str,
    instrument_version: str,
    payload: dict[str, Any],
    client_timestamp: datetime | None,
    existing: list[dict[str, Any]],
) -> dict[str, Any]:
    rule = SUBMISSION_RULES.get(submission_type)
    if rule is None:
        raise Study1ServiceError(
            "UNKNOWN_SUBMISSION_TYPE", "Unknown submission type", 400
        )
    required_phase, roles = rule
    current_phase = session["phase"]
    if current_phase != required_phase.value:
        raise ActionNotAllowedInPhase(current_phase, required_phase.value)
    role = Study1Role(identity["role"])
    if role not in roles:
        raise Study1ServiceError(
            "ACTION_FORBIDDEN_FOR_ROLE", "Role cannot create this submission", 403
        )
    if any(
        item.get("submission_type") == submission_type
        and item.get("participant_id") == identity["participant_id"]
        and item.get("previous_submission_id") is None
        for item in existing
    ):
        raise Study1ServiceError(
            "SUBMISSION_LOCKED",
            "The original submission is locked and cannot be overwritten",
            409,
        )
    if not isinstance(payload, dict):
        raise Study1ServiceError("INVALID_PAYLOAD", "payload must be an object", 400)
    now = utc_now()
    return {
        "submission_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "participant_id": identity["participant_id"],
        "role": role.value,
        "submission_type": submission_type,
        "phase": current_phase,
        "instrument_version": (instrument_version or "1.0")[:64],
        "payload": copy.deepcopy(payload),
        "submitted_at": now,
        "server_timestamp": now,
        "client_timestamp": client_timestamp,
        "locked": True,
        "previous_submission_id": None,
        "revision_operator": None,
        "revision_reason": None,
    }


def _submission_event(
    session: dict[str, Any], submission: dict[str, Any]
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "session_id": submission["session_id"],
        "participant_id": submission["participant_id"],
        "role": submission["role"],
        "phase": session["phase"],
        "phase_version": session["phase_version"],
        "event_type": "submission_created",
        "occurred_at": utc_iso(submission["server_timestamp"]),
        "payload": {
            "submission_id": submission["submission_id"],
            "submission_type": submission["submission_type"],
            "instrument_version": submission["instrument_version"],
        },
    }


def _revision_from(
    original: dict[str, Any],
    operator: str,
    reason: str,
    payload: dict[str, Any],
    instrument_version: str,
) -> dict[str, Any]:
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise Study1ServiceError(
            "REVISION_REASON_REQUIRED", "Revision reason is required", 400
        )
    now = utc_now()
    return {
        **{key: original[key] for key in ("session_id", "participant_id", "role", "phase")},
        "submission_id": str(uuid.uuid4()),
        "submission_type": original["submission_type"],
        "instrument_version": instrument_version or original["instrument_version"],
        "payload": copy.deepcopy(payload),
        "submitted_at": now,
        "server_timestamp": now,
        "client_timestamp": None,
        "locked": True,
        "previous_submission_id": original["submission_id"],
        "revision_operator": operator,
        "revision_reason": clean_reason,
    }


def _validate_review_access(
    session: dict[str, Any] | None, identity: dict[str, Any]
) -> None:
    if not session:
        raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
    if identity.get("role") != Study1Role.PRINCIPAL.value:
        raise Study1ServiceError(
            "REVIEW_ACCESS_FORBIDDEN",
            "Only the principal may access Study 1 review artifacts",
            403,
        )
    if session["phase"] not in (
        Study1Phase.REVIEW.value,
        Study1Phase.COMPREHENSION_MEASUREMENT.value,
    ):
        raise ActionNotAllowedInPhase(session["phase"], Study1Phase.REVIEW.value)
    if not session.get("completion", {}).get("delegation_expectation:principal"):
        raise Study1ServiceError(
            "DELEGATION_EXPECTATION_REQUIRED",
            "Delegation expectation must be submitted before review",
            409,
        )


def _ui_event(
    session: dict[str, Any],
    identity: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "participant_id": identity["participant_id"],
        "role": identity["role"],
        "phase": session["phase"],
        "phase_version": session["phase_version"],
        "event_type": "ui_event",
        "occurred_at": utc_iso(now),
        "payload": {"ui_event_type": event_type, **copy.deepcopy(payload)},
    }


def _record_review_ui_event(
    session: dict[str, Any],
    identity: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    if event_type not in REVIEW_UI_EVENTS:
        raise Study1ServiceError("UNKNOWN_UI_EVENT", "Unknown review UI event", 400)
    safe_payload = copy.deepcopy(payload) if isinstance(payload, dict) else {}
    if event_type == "scroll_depth":
        depth = float(safe_payload.get("max_depth", 0))
        safe_payload["max_depth"] = max(0.0, min(1.0, depth))
        segments = safe_payload.get("visible_segments") or []
        safe_payload["visible_segments"] = [str(value)[:64] for value in segments[:100]]
    if event_type == "transcript_segment_view":
        safe_payload = {"segment_id": str(safe_payload.get("segment_id") or "")[:64]}
    session["completion"]["review_reading_recorded:principal"] = True
    opened = session.get("review_opened_at")
    if opened:
        opened_at = datetime.fromisoformat(opened.replace("Z", "+00:00"))
        elapsed = max(0, int((now - opened_at).total_seconds()))
        safe_payload["server_elapsed_since_review_open_seconds"] = elapsed
        minimum = int(session.get("minimum_review_seconds") or 0)
        if elapsed >= minimum:
            session["completion"]["minimum_review_time_met:principal"] = True
    return _ui_event(session, identity, event_type, safe_payload, now)


def _review_payload(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    latest: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        latest[artifact["type"]] = artifact
    return {
        "summary": latest.get("summary"),
        "transcript": latest.get("transcript"),
    }


def _status_event(
    session: dict[str, Any],
    actor: dict[str, Any],
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "participant_id": actor.get("participant_id"),
        "role": actor.get("role"),
        "phase": session["phase"],
        "phase_version": session["phase_version"],
        "event_type": event_type,
        "occurred_at": utc_iso(),
        "payload": copy.deepcopy(payload or {}),
    }


def _apply_session_control(
    session: dict[str, Any],
    action: str,
    actor: dict[str, Any],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    if actor.get("role") != Study1Role.RESEARCHER.value:
        raise Study1ServiceError("FORBIDDEN", "Researcher role required", 403)
    events: list[dict[str, Any]] = []
    status = session["status"]
    if action == "start":
        if status != "waiting" or session["phase"] != Study1Phase.SETUP.value:
            raise Study1ServiceError(
                "SESSION_CANNOT_START", "Session must be waiting in SETUP", 409
            )
        session["status"] = "running"
        events.append(_status_event(session, actor, "session_start"))
        transition = transition_phase(
            session,
            Study1Phase.MATERIAL_READING,
            actor,
            reason="researcher_started_session",
        )
        events.extend(_transition_events(session["session_id"], actor, transition))
    elif action == "pause":
        if status != "running":
            raise Study1ServiceError(
                "SESSION_CANNOT_PAUSE", "Only a running session can be paused", 409
            )
        session["status"] = "paused"
        events.append(_status_event(session, actor, "session_pause"))
    elif action == "resume":
        if status != "paused":
            raise Study1ServiceError(
                "SESSION_CANNOT_RESUME", "Only a paused session can be resumed", 409
            )
        session["status"] = "running"
        events.append(_status_event(session, actor, "session_resume"))
    elif action == "extend":
        seconds = int(payload.get("seconds") or 0)
        if seconds <= 0 or seconds > 86400:
            raise Study1ServiceError(
                "INVALID_EXTENSION", "seconds must be between 1 and 86400", 400
            )
        session["remaining_seconds"] = int(session.get("remaining_seconds") or 0) + seconds
        events.append(
            _status_event(
                session,
                actor,
                "session_extend",
                {"seconds": seconds, "remaining_seconds": session["remaining_seconds"]},
            )
        )
    elif action == "terminate":
        if status in ("terminated", "completed"):
            raise Study1ServiceError(
                "SESSION_CANNOT_TERMINATE", "Session is already terminal", 409
            )
        session["status"] = "terminated"
        events.append(
            _status_event(
                session,
                actor,
                "session_terminate",
                {"reason": str(payload.get("reason") or "").strip() or None},
            )
        )
    else:
        raise Study1ServiceError("UNKNOWN_CONTROL_ACTION", "Unknown control action", 400)
    return events


def _new_incident(
    session_id: str,
    actor: dict[str, Any],
    category: str,
    severity: str,
    description: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    clean_description = (description or "").strip()
    if not clean_description:
        raise Study1ServiceError(
            "INCIDENT_DESCRIPTION_REQUIRED", "Incident description is required", 400
        )
    allowed_severity = {"info", "warning", "critical"}
    if severity not in allowed_severity:
        raise Study1ServiceError("INVALID_INCIDENT_SEVERITY", "Invalid severity", 400)
    return {
        "incident_id": str(uuid.uuid4()),
        "session_id": session_id,
        "category": (category or "other")[:64],
        "severity": severity,
        "description": clean_description,
        "created_at": utc_now(),
        "created_by": actor.get("participant_id") or "researcher",
        "metadata": copy.deepcopy(metadata or {}),
    }


def _incident_event(
    session: dict[str, Any],
    actor: dict[str, Any],
    incident: dict[str, Any],
) -> dict[str, Any]:
    return _status_event(
        session,
        actor,
        "incident_created",
        {
            "incident_id": incident["incident_id"],
            "category": incident["category"],
            "severity": incident["severity"],
        },
    )


def _participant_status_event(
    session: dict[str, Any], identity: dict[str, Any], online: bool
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "participant_id": identity["participant_id"],
        "role": identity["role"],
        "phase": session["phase"],
        "phase_version": session["phase_version"],
        "event_type": "participant_status_updated",
        "occurred_at": utc_iso(),
        "payload": {"online": bool(online)},
    }


def _dashboard_payload(
    session: dict[str, Any],
    artifacts: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
) -> dict[str, Any]:
    state = readiness(session)
    completion = session.get("completion") or {}
    participant_status = []
    for participant in session.get("participants") or []:
        role = participant["role"]
        participant_status.append(
            {
                **participant,
                "completed_actions": sorted(
                    key for key, value in completion.items() if value and key.endswith(f":{role}")
                ),
            }
        )
    types = {item["type"] for item in artifacts}
    return {
        "session_id": session["session_id"],
        "session_name": session["session_name"],
        "phase": session["phase"],
        "phase_version": session["phase_version"],
        "phase_started_at": session["phase_started_at"],
        "status": session["status"],
        "participants": participant_status,
        "not_submitted": state["missing_prerequisites"],
        **state,
        "media_service_status": session.get("media_service_status", "mock_idle"),
        "artifacts": {
            "summary": "ready" if "summary" in types else "pending",
            "transcript": "ready" if "transcript" in types else "pending",
        },
        "incident_count": len(incidents),
        "remaining_seconds": session.get("remaining_seconds"),
    }


def _media_command_event(
    session: dict[str, Any], envelope: dict[str, Any], key: str
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "participant_id": "researcher",
        "role": Study1Role.RESEARCHER.value,
        "phase": session["phase"],
        "phase_version": session["phase_version"],
        "event_type": "media_command",
        "occurred_at": envelope["issued_at"],
        "payload": copy.deepcopy(envelope),
        "idempotency_key": key,
    }


def _media_event_log(
    session: dict[str, Any], envelope: dict[str, Any], key: str
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "participant_id": None,
        "role": "proxy",
        "phase": session["phase"],
        "phase_version": session["phase_version"],
        "event_type": "media_event",
        "occurred_at": envelope["occurred_at"],
        "payload": copy.deepcopy(envelope),
        "idempotency_key": key,
    }


def _apply_media_event(session: dict[str, Any], envelope: dict[str, Any]) -> None:
    if int(envelope["phase_version"]) != int(session["phase_version"]):
        raise Study1ServiceError(
            "STALE_MEDIA_EVENT", "Media event phase_version is stale", 409
        )
    event_type = envelope["event_type"]
    if event_type not in EVENT_TYPES:
        raise Study1ServiceError("UNKNOWN_MEDIA_EVENT", "Unknown media event type", 400)
    if event_type == "MEDIA_READY":
        session["media_service_status"] = "ready"
    elif event_type == "MEDIA_ERROR":
        session["media_service_status"] = "error"
    elif event_type == "HANDOFF_COMPLETE":
        if session["phase"] != Study1Phase.HANDOFF.value:
            raise ActionNotAllowedInPhase(session["phase"], Study1Phase.HANDOFF.value)
        session["completion"]["handoff_complete"] = True
    elif event_type == "MEETING_ENDED":
        if session["phase"] == Study1Phase.PROXY_MEETING.value:
            session["completion"]["proxy_meeting_ended"] = True
        elif session["phase"] == Study1Phase.SYNC_MEETING.value:
            session["completion"]["sync_meeting_ended"] = True
        else:
            raise Study1ServiceError(
                "MEETING_END_NOT_ALLOWED",
                "MEETING_ENDED is valid only in a meeting phase",
                409,
            )


def _artifact_ready_event(
    session: dict[str, Any], artifact: dict[str, Any]
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "participant_id": None,
        "role": "proxy",
        "phase": session["phase"],
        "phase_version": session["phase_version"],
        "event_type": "artifact_ready",
        "occurred_at": utc_iso(artifact["created_at"]),
        "payload": {
            "artifact_id": artifact["artifact_id"],
            "type": artifact["type"],
            "version": artifact["version"],
        },
    }


class Study1Service:
    def __init__(
        self,
        repository: InMemoryStudy1Repository | SqlAlchemyStudy1Repository,
        token_manager: Study1TokenManager | None = None,
        media_gateway: MediaGateway | None = None,
    ):
        self.repository = repository
        self.tokens = token_manager or Study1TokenManager()
        self.media_gateway = media_gateway or MockMediaGateway()

    def create_session(
        self,
        session_name: str,
        invite_ttl_seconds: int = 86400,
        materials_by_role: dict[str, list[dict[str, Any]]] | None = None,
        minimum_review_seconds: int = 0,
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
            "minimum_review_seconds": max(0, int(minimum_review_seconds)),
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
        materials = _normalize_materials(session_id, materials_by_role or {}, now)
        self.repository.create_session(snapshot, rows, materials)
        return {
            "session": self.session_dto(snapshot),
            "invites": [invite.public_dict() for invite in created],
        }

    def get_materials(self, session_id: str, role: Study1Role | str) -> list[dict[str, Any]]:
        role_value = Study1Role(role)
        if role_value not in HUMAN_ROLES:
            raise Study1ServiceError(
                "MATERIAL_ACCESS_FORBIDDEN", "Role cannot access participant materials", 403
            )
        return self.repository.list_materials(session_id, role_value.value)

    def add_materials(
        self, session_id: str, role: Study1Role | str, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if self.repository.get_session(session_id) is None:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        rows = _normalize_materials(session_id, {Study1Role(role).value: items}, utc_now())
        self.repository.add_materials(rows)
        return rows

    def add_uploaded_materials(
        self, session_id: str, role: Study1Role | str, files
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for index, upload in enumerate(files, start=1):
            raw = upload.read()
            if len(raw) > 20 * 1024 * 1024:
                raise Study1ServiceError(
                    "MATERIAL_TOO_LARGE", "Each material must be at most 20 MB", 413
                )
            filename = (upload.filename or "").lower()
            if filename.endswith(".pdf"):
                try:
                    import pdfplumber

                    with pdfplumber.open(io.BytesIO(raw)) as pdf:
                        content = "\n\n".join(
                            page.extract_text() or "" for page in pdf.pages
                        ).strip()
                        page_count = len(pdf.pages)
                except Exception as error:
                    raise Study1ServiceError(
                        "MATERIAL_PARSE_FAILED", "Unable to extract PDF text", 422
                    ) from error
            elif filename.endswith((".txt", ".md")):
                try:
                    content = raw.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise Study1ServiceError(
                        "MATERIAL_PARSE_FAILED", "Text material must be UTF-8", 422
                    ) from error
                page_count = None
            else:
                raise Study1ServiceError(
                    "UNSUPPORTED_MATERIAL_TYPE",
                    "Study 1 material uploads must be PDF, TXT, or Markdown",
                    400,
                )
            if not content.strip():
                raise Study1ServiceError(
                    "EMPTY_MATERIAL", "Uploaded material contains no extractable text", 422
                )
            items.append(
                {
                    # Do not persist original filenames: they may contain real names.
                    "title": f"Uploaded material {index}",
                    "content": content,
                    "metadata": {
                        "content_type": upload.mimetype or "application/octet-stream",
                        "page_count": page_count,
                        "source": "researcher_upload",
                    },
                }
            )
        return self.add_materials(session_id, role, items)

    def submit(
        self,
        session_id: str,
        identity: dict[str, Any],
        submission_type: str,
        instrument_version: str,
        payload: dict[str, Any],
        client_timestamp: str | None = None,
    ) -> dict[str, Any]:
        parsed_client_time = None
        if client_timestamp:
            try:
                parsed_client_time = datetime.fromisoformat(
                    client_timestamp.replace("Z", "+00:00")
                )
            except ValueError as error:
                raise Study1ServiceError(
                    "INVALID_CLIENT_TIMESTAMP",
                    "client_timestamp must be ISO-8601",
                    400,
                ) from error
        return self.repository.create_submission(
            session_id,
            identity,
            submission_type,
            instrument_version,
            payload,
            parsed_client_time,
        )

    def revise_submission(
        self,
        session_id: str,
        submission_id: str,
        operator: str,
        reason: str,
        payload: dict[str, Any],
        instrument_version: str,
    ) -> dict[str, Any]:
        return self.repository.create_revision(
            session_id,
            submission_id,
            operator,
            reason,
            payload,
            instrument_version,
        )

    def advance(
        self,
        session_id: str,
        actor: dict[str, Any],
        target_phase: str,
        reason: str | None = None,
        override: bool = False,
    ) -> dict[str, Any]:
        try:
            snapshot, events = self.repository.transition(
                session_id, target_phase, actor, reason, override
            )
            return {"session": self.session_dto(snapshot), "events": events}
        except OverrideReasonRequired as error:
            raise Study1ServiceError(
                "OVERRIDE_REASON_REQUIRED", str(error), 400
            ) from error
        except PrerequisitesNotMet as error:
            raise Study1ServiceError(
                "PREREQUISITES_NOT_MET", str(error), 409
            ) from error
        except (InvalidTransition, ValueError) as error:
            raise Study1ServiceError(
                "INVALID_PHASE_TRANSITION", str(error), 409
            ) from error

    def list_sessions(self) -> list[dict[str, Any]]:
        return [
            self.session_dto(snapshot)
            | {"session_name": snapshot["session_name"]}
            for snapshot in self.repository.list_sessions()
        ]

    def control(
        self,
        session_id: str,
        actor: dict[str, Any],
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot, events = self.repository.control_session(
            session_id, action, actor, payload or {}
        )
        return {"session": self.session_dto(snapshot), "events": events}

    def add_incident(
        self,
        session_id: str,
        actor: dict[str, Any],
        category: str,
        severity: str,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.repository.add_incident(
            session_id,
            actor,
            category,
            severity,
            description,
            metadata or {},
        )

    def participant_status(
        self, session_id: str, identity: dict[str, Any], online: bool
    ) -> None:
        self.repository.participant_status(session_id, identity, online)

    def researcher_dashboard(self, session_id: str) -> dict[str, Any]:
        return self.repository.dashboard(session_id)

    def issue_media_command(
        self,
        session_id: str,
        actor: dict[str, Any],
        command: str,
        payload: dict[str, Any] | None = None,
        command_id: str | None = None,
    ) -> dict[str, Any]:
        if actor.get("role") != Study1Role.RESEARCHER.value:
            raise Study1ServiceError("FORBIDDEN", "Researcher role required", 403)
        if command not in COMMANDS:
            raise Study1ServiceError("UNKNOWN_MEDIA_COMMAND", "Unknown command", 400)
        session = self.repository.get_session(session_id)
        if not session:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        required = {
            "START_PROXY_MEETING": Study1Phase.PROXY_MEETING.value,
            "BEGIN_HANDOFF": Study1Phase.HANDOFF.value,
            "START_SYNC_MEETING": Study1Phase.SYNC_MEETING.value,
        }.get(command)
        if required and session["phase"] != required:
            raise ActionNotAllowedInPhase(session["phase"], required)
        envelope = {
            "command_id": command_id or str(uuid.uuid4()),
            "session_id": session_id,
            "phase_version": session["phase_version"],
            "command": command,
            "issued_at": utc_iso(),
            "payload": copy.deepcopy(payload or {}),
        }
        created = self.repository.record_media_command(session_id, envelope)
        result = (
            self.media_gateway.send_command(envelope)
            if created
            else {
                "accepted": True,
                "duplicate": True,
                "command_id": envelope["command_id"],
                "mode": "idempotent-replay",
            }
        )
        return {"command": envelope, "duplicate": not created, "gateway": result}

    def receive_media_event(self, data: dict[str, Any]) -> dict[str, Any]:
        envelope = _validate_media_event_envelope(data)
        processed, snapshot = self.repository.record_media_event(envelope)
        return {
            "processed": processed,
            "duplicate": not processed,
            "session": self.session_dto(snapshot),
        }

    def create_artifact(
        self, session_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        artifact = _validate_artifact(session_id, data)
        created, value = self.repository.create_artifact(session_id, artifact)
        return {"created": created, "duplicate": not created, "artifact": value}

    def export_bundle(self, session_id: str):
        from .export_service import build_study1_export

        return build_study1_export(self.repository.export_data(session_id))

    def get_review(
        self, session_id: str, identity: dict[str, Any]
    ) -> dict[str, Any]:
        return self.repository.open_review(session_id, identity)

    def log_review_ui_event(
        self,
        session_id: str,
        identity: dict[str, Any],
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self.repository.record_ui_event(
            session_id, identity, event_type, payload
        )

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
            "remaining_seconds": snapshot.get("remaining_seconds"),
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


def _normalize_materials(
    session_id: str,
    materials_by_role: dict[str, list[dict[str, Any]]],
    created_at: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    allowed = {role.value for role in HUMAN_ROLES}
    for role, items in materials_by_role.items():
        if role not in allowed:
            raise Study1ServiceError(
                "INVALID_MATERIAL_ROLE", f"Invalid material role: {role}", 400
            )
        if not isinstance(items, list):
            raise Study1ServiceError(
                "INVALID_MATERIALS", "Each role's materials must be a list", 400
            )
        for item in items:
            if not isinstance(item, dict):
                raise Study1ServiceError(
                    "INVALID_MATERIALS", "Each material must be an object", 400
                )
            content = item.get("content")
            storage_uri = item.get("storage_uri")
            if content is None and not storage_uri:
                raise Study1ServiceError(
                    "INVALID_MATERIAL", "Material requires content or storage_uri", 400
                )
            checksum_source = (
                str(content).encode("utf-8")
                if content is not None
                else str(storage_uri).encode("utf-8")
            )
            rows.append(
                {
                    "material_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "role": role,
                    "title": str(item.get("title") or "Material")[:512],
                    "content": str(content) if content is not None else None,
                    "storage_uri": str(storage_uri) if storage_uri else None,
                    "checksum": hashlib.sha256(checksum_source).hexdigest(),
                    "created_at": created_at,
                    "metadata_payload": copy.deepcopy(item.get("metadata") or {}),
                }
            )
    return rows


def _validate_media_event_envelope(data: dict[str, Any]) -> dict[str, Any]:
    required = (
        "event_id",
        "session_id",
        "phase_version",
        "event_type",
        "occurred_at",
    )
    missing = [key for key in required if data.get(key) in (None, "")]
    if missing:
        raise Study1ServiceError(
            "INVALID_MEDIA_EVENT", "Missing fields: " + ", ".join(missing), 400
        )
    if data["event_type"] not in EVENT_TYPES:
        raise Study1ServiceError("UNKNOWN_MEDIA_EVENT", "Unknown media event type", 400)
    return {
        "event_id": str(data["event_id"]),
        "session_id": str(data["session_id"]),
        "phase_version": int(data["phase_version"]),
        "event_type": str(data["event_type"]),
        "occurred_at": str(data["occurred_at"]),
        "payload": copy.deepcopy(data.get("payload") or {}),
    }


def _validate_artifact(session_id: str, data: dict[str, Any]) -> dict[str, Any]:
    allowed = {"transcript", "summary", "recording_manifest", "agent_log_manifest"}
    artifact_type = str(data.get("type") or "")
    if artifact_type not in allowed:
        raise Study1ServiceError("INVALID_ARTIFACT_TYPE", "Invalid artifact type", 400)
    content = data.get("content")
    storage_uri = data.get("storage_uri")
    if content is None and not storage_uri:
        raise Study1ServiceError(
            "INVALID_ARTIFACT", "content or storage_uri is required", 400
        )
    checksum_source = (
        str(content).encode("utf-8")
        if content is not None
        else str(storage_uri).encode("utf-8")
    )
    computed = hashlib.sha256(checksum_source).hexdigest()
    provided_checksum = str(data.get("checksum") or computed)
    if content is not None and provided_checksum != computed:
        raise Study1ServiceError("CHECKSUM_MISMATCH", "Artifact checksum mismatch", 422)
    created_at = data.get("created_at")
    if created_at:
        try:
            created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except ValueError as error:
            raise Study1ServiceError(
                "INVALID_ARTIFACT_TIMESTAMP", "created_at must be ISO-8601", 400
            ) from error
    else:
        created = utc_now()
    return {
        "artifact_id": str(data.get("artifact_id") or uuid.uuid4()),
        "session_id": session_id,
        "type": artifact_type,
        "version": str(data.get("version") or "1"),
        "content": str(content) if content is not None else None,
        "storage_uri": str(storage_uri) if storage_uri else None,
        "checksum": provided_checksum,
        "created_at": created,
        "generator_version": str(data.get("generator_version") or "unknown"),
        "metadata": copy.deepcopy(data.get("metadata") or {}),
    }
