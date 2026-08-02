"""Study 1 application service and persistence adapters."""

from __future__ import annotations

import hashlib
import copy
import io
import json
import math
import os
import random
import re
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, MutableMapping

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from services.db import ResearchSessionRow, get_session_factory, is_db_configured

from .models import (
    HUMAN_ROLES,
    Study1EventRow,
    Study1ArtifactRow,
    Study1InviteRow,
    Study1IncidentRow,
    Study1FactAssignmentRow,
    Study1MarkerRow,
    Study1MaterialRow,
    Study1Phase,
    Study1Role,
    Study1RoleAssignmentRow,
    Study1ProtocolSnapshotRow,
    Study1ReplayPlanRow,
    Study1DecisionRow,
    Study1InstrumentResponseRow,
    Study1SharedArtifactRow,
    Study1SharedConfirmationRow,
    Study1SharedRevisionRow,
    Study1SubmissionRow,
    Study1TaskDefinitionRow,
    Study1TaskFactRow,
)
from .media_gateway import (
    COMMANDS,
    EVENT_TYPES,
    MediaGateway,
    MediaGatewayError,
    create_media_gateway_from_env,
)
from .permissions import Study1TokenManager
from .state_machine import (
    InvalidTransition,
    OverrideReasonRequired,
    PrerequisitesNotMet,
    readiness,
    transition_phase,
)
from .task_registry import TaskDefinitionValidationError, validate_registered_task
from .protocol_config import (
    ProtocolConfigError,
    assert_protocol_runtime_match,
    clone_protocol_values,
    compute_protocol_checksum,
    formal_protocol_defaults,
    freeze_protocol_snapshot,
    normalize_protocol_config_v2,
)
from .action_policy import ActionPolicyViolation, authorize_action
from .decisions import DecisionKind, DecisionValidationError, validate_individual_decision
from .instruments import (
    InstrumentValidationError,
    instrument_for,
    load_instrument_catalog,
    validate_ordered_responses,
)
from .shared_artifacts import (
    SharedArtifactKind,
    SharedArtifactValidationError,
    content_checksum,
    validate_shared_artifact_context,
    validate_shared_content,
)
from .summary_service import (
    SummaryPolicyError,
    SummaryQaService,
    build_summary_failure_action,
)
from .incident_codes import IncidentCodeError, incident_definition
from .quality_service import build_quality_snapshot, normalize_rtc_metric
from .marker_service import (
    MarkerValidationError,
    marker_visible_to_actor,
    normalize_marker,
)
from .replay_service import ReplayValidationError, build_replay_plan
from .privacy_service import (
    missing_required_consent_scopes,
    normalize_consent_submission,
)
from .review_telemetry import ReviewTelemetryAccumulator
from .formal_projection import (
    formal_capabilities,
    formal_readiness,
    project_formal_session,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def study1_release_identity_from_env() -> dict[str, str] | None:
    release_id = os.environ.get("STUDY1_RELEASE_ID")
    checksum = os.environ.get("STUDY1_RELEASE_CHECKSUM")
    if not release_id and not checksum:
        return None
    return {"release_id": str(release_id or ""), "checksum": str(checksum or "")}


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
    "consent": (Study1Phase.SETUP, HUMAN_ROLES),
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

PROXY_AUTHORITY_LEVELS = {
    "share_only",
    "suggest",
    "agree_tentative",
}

STRUCTURED_SUBMISSION_FIELDS: dict[str, tuple[str, ...]] = {
    "consent": (
        "consent_version",
        "identity_confirmed",
        "role_confirmed",
        "voluntary_participation_confirmed",
    ),
    "pre_vote": ("decision", "rationale", "confidence"),
    "proxy_config": (
        "priorities",
        "boundaries",
        "authority_level",
        "authorization_confirmed",
        "authorized_material_ids",
    ),
    "tentative_decision": (
        "decision",
        "rationale",
        "confidence",
        "decision_status",
        "proxy_authority_belief",
        "expected_principal_acceptance",
    ),
    "delegation_expectation": (
        "expected_information_shared",
        "expected_recommendation",
        "expected_tentative_agreement",
        "confidence",
    ),
    "comprehension_measurement": (
        "conclusion",
        "reasons",
        "member_positions",
        "disagreements",
        "decision_status",
        "proxy_commitments",
        "acceptance_intention",
        "confidence",
    ),
    "final_decision": (
        "decision",
        "rationale",
        "confidence",
        "decision_scope",
    ),
    "followup_task": (
        "resource_allocation",
        "action_ranking",
        "implementation_plan",
    ),
    "post_survey": (
        "understanding",
        "proxy_trust",
        "team_synchronization",
        "comments",
    ),
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
    "critical_marker",
    "recording_replay",
    "rtc_metric_sample",
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
        self.task_definitions: dict[tuple[str, str], dict[str, Any]] = {}
        self.role_assignments: list[dict[str, Any]] = []
        self.fact_assignments: list[dict[str, Any]] = []
        self.protocol_snapshots: dict[str, dict[str, Any]] = {}
        self.decisions: list[dict[str, Any]] = []
        self.instrument_responses: list[dict[str, Any]] = []
        self.shared_artifacts: dict[tuple[str, str], dict[str, Any]] = {}
        self.shared_revisions: list[dict[str, Any]] = []
        self.shared_confirmations: list[dict[str, Any]] = []
        self.markers: list[dict[str, Any]] = []
        self.replay_plans: list[dict[str, Any]] = []
        self.idempotency_keys: set[str] = set()
        self._lock = threading.RLock()

    def create_session(
        self,
        snapshot: dict[str, Any],
        invites: list[dict[str, Any]],
        materials: list[dict[str, Any]] | None = None,
        role_assignments: list[dict[str, Any]] | None = None,
        fact_assignments: list[dict[str, Any]] | None = None,
        initial_events: list[dict[str, Any]] | None = None,
        protocol_snapshot: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self.sessions[snapshot["session_id"]] = copy.deepcopy(snapshot)
            for invite in invites:
                self.invites[invite["token_hash"]] = copy.deepcopy(invite)
            self.materials.extend(copy.deepcopy(materials or []))
            self.role_assignments.extend(copy.deepcopy(role_assignments or []))
            self.fact_assignments.extend(copy.deepcopy(fact_assignments or []))
            self.events.extend(copy.deepcopy(initial_events or []))
            if protocol_snapshot is not None:
                self.protocol_snapshots[snapshot["session_id"]] = copy.deepcopy(
                    protocol_snapshot
                )

    def get_protocol_snapshot(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self.protocol_snapshots.get(session_id)
            return copy.deepcopy(value) if value else None

    def update_protocol_snapshot(
        self, session_id: str, protocol_snapshot: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            self.protocol_snapshots[session_id] = copy.deepcopy(protocol_snapshot)
            config = copy.deepcopy(protocol_snapshot.get("canonical_config") or {})
            session["experiment_config"] = config
            session["configuration_checksum"] = protocol_snapshot.get("checksum")
            session["protocol_snapshot_id"] = protocol_snapshot.get(
                "protocol_snapshot_id"
            )
            session["protocol_config_frozen"] = bool(protocol_snapshot.get("frozen"))
            return copy.deepcopy(protocol_snapshot)

    def create_task_definition(self, task: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            key = (task["task_definition_id"], task["task_version"])
            if key in self.task_definitions:
                raise Study1ServiceError(
                    "TASK_DEFINITION_EXISTS", "Task definition already exists", 409
                )
            self.task_definitions[key] = copy.deepcopy(task)
            return copy.deepcopy(task)

    def get_task_definition(
        self, task_definition_id: str, task_version: str | None = None
    ) -> dict[str, Any] | None:
        """Resolve an exact version, or the newest definition for legacy callers."""
        with self._lock:
            if task_version is not None:
                value = self.task_definitions.get(
                    (task_definition_id, task_version)
                )
            else:
                matches = [
                    item
                    for (logical_id, _version), item in self.task_definitions.items()
                    if logical_id == task_definition_id
                ]
                value = max(
                    matches,
                    key=lambda item: (item["created_at"], item["task_version"]),
                    default=None,
                )
            return copy.deepcopy(value) if value else None

    def replace_task_definition(
        self, task_definition_id: str, task: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            key = (task_definition_id, task["task_version"])
            current = self.task_definitions.get(key)
            if current is None:
                raise Study1ServiceError(
                    "TASK_DEFINITION_NOT_FOUND", "Task definition not found", 404
                )
            if current["status"] != "draft":
                raise Study1ServiceError(
                    "TASK_DEFINITION_IMMUTABLE",
                    "Validated task definitions cannot be modified",
                    409,
                )
            self.task_definitions[key] = copy.deepcopy(task)
            return copy.deepcopy(task)

    def set_task_definition_status(
        self,
        task_definition_id: str,
        task_version: str,
        status: str,
        content_checksum: str,
    ) -> dict[str, Any]:
        with self._lock:
            task = self.task_definitions.get((task_definition_id, task_version))
            if task is None:
                raise Study1ServiceError(
                    "TASK_DEFINITION_NOT_FOUND", "Task definition not found", 404
                )
            if task["content_checksum"] != content_checksum:
                raise Study1ServiceError(
                    "TASK_DEFINITION_CHANGED",
                    "Task definition changed before validation completed",
                    409,
                )
            if task["status"] == status:
                return copy.deepcopy(task)
            if task["status"] != "draft":
                raise Study1ServiceError(
                    "TASK_DEFINITION_IMMUTABLE",
                    "Validated task definitions cannot be modified",
                    409,
                )
            task["status"] = status
            return copy.deepcopy(task)

    def list_task_definitions(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            values = self.task_definitions.values()
            return [
                copy.deepcopy(item)
                for item in sorted(
                    values,
                    key=lambda value: (
                        value["task_definition_id"],
                        value["task_version"],
                    ),
                )
                if status is None or item["status"] == status
            ]

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
        completion_override: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with self._lock:
            stored = self.sessions.get(session_id)
            if not stored:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            session = copy.deepcopy(stored)
            if completion_override is not None:
                session["completion"] = copy.deepcopy(dict(completion_override))
            transition = transition_phase(
                session, target_phase, actor, reason=reason, override=override
            )
            if session["phase"] == Study1Phase.COMPLETED.value:
                session["status"] = "completed"
            if completion_override is not None:
                session["completion"] = copy.deepcopy(stored.get("completion") or {})
            self.sessions[session_id] = session
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

    def create_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if any(
                row["session_id"] == decision["session_id"]
                and row["decision_kind"] == decision["decision_kind"]
                and row.get("participant_id") == decision.get("participant_id")
                for row in self.decisions
            ):
                raise Study1ServiceError("DECISION_ALREADY_SUBMITTED", "Decision already submitted", 409)
            self.decisions.append(copy.deepcopy(decision))
            return copy.deepcopy(decision)

    def mark_completion(self, session_id: str, key: str) -> None:
        with self._lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            session.setdefault("completion", {})[key] = True

    def list_decisions(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(row) for row in self.decisions if row["session_id"] == session_id]

    def create_instrument_response(self, response: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if any(
                row["session_id"] == response["session_id"]
                and row["participant_id"] == response["participant_id"]
                and row["instrument_definition_id"] == response["instrument_definition_id"]
                and row["instrument_version"] == response["instrument_version"]
                for row in self.instrument_responses
            ):
                raise Study1ServiceError("INSTRUMENT_ALREADY_SUBMITTED", "Instrument already submitted", 409)
            self.instrument_responses.append(copy.deepcopy(response))
            return copy.deepcopy(response)

    def get_shared_artifact(
        self, session_id: str, kind: str
    ) -> dict[str, Any] | None:
        with self._lock:
            artifact = self.shared_artifacts.get((session_id, kind))
            if artifact is None:
                return None
            return _shared_artifact_projection(
                artifact,
                [
                    row
                    for row in self.shared_revisions
                    if row["shared_artifact_id"] == artifact["shared_artifact_id"]
                ],
                self.shared_confirmations,
            )

    def create_shared_revision(
        self,
        session_id: str,
        kind: str,
        parent_revision_id: str | None,
        content: dict[str, Any],
        identity: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            key = (session_id, kind)
            artifact = self.shared_artifacts.get(key)
            now = utc_now()
            if artifact is None:
                if parent_revision_id is not None:
                    raise Study1ServiceError(
                        "SHARED_REVISION_CONFLICT",
                        "parent_revision_id does not match the current revision",
                        409,
                    )
                artifact = {
                    "shared_artifact_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "kind": kind,
                    "current_revision_id": None,
                    "locked_revision_id": None,
                    "locked_at": None,
                    "created_at": now,
                }
                self.shared_artifacts[key] = artifact
            if artifact.get("locked_revision_id"):
                raise Study1ServiceError(
                    "SHARED_ARTIFACT_LOCKED", "Shared artifact is already locked", 409
                )
            if parent_revision_id != artifact.get("current_revision_id"):
                raise Study1ServiceError(
                    "SHARED_REVISION_CONFLICT",
                    "parent_revision_id does not match the current revision",
                    409,
                )
            revision_number = 1 + sum(
                1
                for row in self.shared_revisions
                if row["shared_artifact_id"] == artifact["shared_artifact_id"]
            )
            revision = {
                "revision_id": str(uuid.uuid4()),
                "shared_artifact_id": artifact["shared_artifact_id"],
                "revision_number": revision_number,
                "parent_revision_id": parent_revision_id,
                "content": copy.deepcopy(content),
                "content_checksum": content_checksum(content),
                "editor_participant_id": identity["participant_id"],
                "editor_role": identity["role"],
                "created_at": now,
            }
            self.shared_revisions.append(revision)
            artifact["current_revision_id"] = revision["revision_id"]
            self.events.append(
                _shared_artifact_event(
                    session,
                    identity,
                    "shared_revision_created",
                    {
                        "kind": kind,
                        "revision_id": revision["revision_id"],
                        "revision_number": revision_number,
                        "parent_revision_id": parent_revision_id,
                        "content_checksum": revision["content_checksum"],
                    },
                    now,
                )
            )
            return _shared_revision_projection(revision, [], artifact)

    def confirm_shared_revision(
        self,
        session_id: str,
        kind: str,
        revision_id: str,
        identity: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            session = self.sessions.get(session_id)
            artifact = self.shared_artifacts.get((session_id, kind))
            if session is None:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            if artifact is None or artifact.get("current_revision_id") != revision_id:
                raise Study1ServiceError(
                    "SHARED_REVISION_NOT_CURRENT",
                    "Only the current revision can be confirmed",
                    409,
                )
            revision = next(
                (
                    row
                    for row in self.shared_revisions
                    if row["revision_id"] == revision_id
                ),
                None,
            )
            if revision is None:
                raise Study1ServiceError(
                    "SHARED_REVISION_NOT_FOUND", "Shared revision not found", 404
                )
            existing = next(
                (
                    row
                    for row in self.shared_confirmations
                    if row["revision_id"] == revision_id
                    and row["participant_id"] == identity["participant_id"]
                ),
                None,
            )
            now = utc_now()
            if existing is None:
                confirmation = {
                    "confirmation_id": str(uuid.uuid4()),
                    "revision_id": revision_id,
                    "participant_id": identity["participant_id"],
                    "role": identity["role"],
                    "confirmed_at": now,
                }
                self.shared_confirmations.append(confirmation)
                self.events.append(
                    _shared_artifact_event(
                        session,
                        identity,
                        "shared_revision_confirmed",
                        {"kind": kind, "revision_id": revision_id},
                        now,
                    )
                )
            confirmations = [
                row
                for row in self.shared_confirmations
                if row["revision_id"] == revision_id
            ]
            roles = {row["role"] for row in confirmations}
            if roles == {role.value for role in HUMAN_ROLES} and not artifact.get(
                "locked_revision_id"
            ):
                artifact["locked_revision_id"] = revision_id
                artifact["locked_at"] = now
                _apply_shared_lock_to_snapshot(session, kind)
                if kind == SharedArtifactKind.TEAM_FINAL.value:
                    self.decisions.append(
                        _team_final_decision(session_id, revision, now)
                    )
                self.events.append(
                    _shared_artifact_event(
                        session,
                        identity,
                        "shared_artifact_locked",
                        {"kind": kind, "revision_id": revision_id},
                        now,
                    )
                )
            return _shared_revision_projection(revision, confirmations, artifact)

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
            if event_type == "rtc_metric_sample":
                _validate_rtc_telemetry_access(session, identity)
            else:
                _validate_review_access(session, identity)
            event = _record_review_ui_event(
                session, identity, event_type, payload, utc_now()
            )
            self.events.append(event)
            return copy.deepcopy(event)

    def record_review_event_batch(
        self,
        session_id: str,
        identity: dict[str, Any],
        visit_id: str,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        with self._lock:
            session = self.sessions.get(session_id)
            _validate_review_access(session, identity)
            result = _record_review_event_batch(
                session, identity, visit_id, events, utc_now()
            )
            self.events.append(result["event"])
            return copy.deepcopy(result["response"])

    def create_marker(
        self,
        session_id: str,
        actor: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            marker = normalize_marker(
                session_id=session_id,
                actor=actor,
                payload=payload,
                created_at=utc_now(),
            )
            self.markers.append(copy.deepcopy(marker))
            self.events.append(_marker_event(session, actor, marker))
            return copy.deepcopy(marker)

    def list_markers(
        self, session_id: str, actor: dict[str, Any]
    ) -> list[dict[str, Any]]:
        with self._lock:
            if session_id not in self.sessions:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            markers = [
                item
                for item in self.markers
                if item["session_id"] == session_id and marker_visible_to_actor(item, actor)
            ]
            return copy.deepcopy(
                sorted(markers, key=lambda item: (item["start_ms"], item["created_at"]))
            )

    def create_replay_plan(
        self,
        session_id: str,
        actor: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            marker_ids = _normalize_optional_string_set(payload.get("marker_ids"))
            markers = [
                marker
                for marker in self.markers
                if marker["session_id"] == session_id
                and (not marker_ids or marker["marker_id"] in marker_ids)
            ]
            plan = build_replay_plan(
                session_id=session_id,
                markers=copy.deepcopy(markers),
                existing_count=len(
                    [
                        item
                        for item in self.replay_plans
                        if item["session_id"] == session_id
                    ]
                ),
                created_by=str(actor.get("participant_id") or actor.get("role") or ""),
                context_seconds=int(payload.get("context_seconds", 10)),
                created_at=utc_now(),
            )
            self.replay_plans.append(copy.deepcopy(plan))
            self.events.append(_replay_plan_event(session, actor, plan))
            return copy.deepcopy(plan)

    def list_replay_plans(
        self, session_id: str, actor: dict[str, Any]
    ) -> list[dict[str, Any]]:
        with self._lock:
            if actor.get("role") != Study1Role.RESEARCHER.value:
                raise Study1ServiceError("FORBIDDEN", "Researcher role required", 403)
            if session_id not in self.sessions:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            return copy.deepcopy(
                [
                    item
                    for item in sorted(
                        self.replay_plans,
                        key=lambda row: (row["session_id"], row["created_at"]),
                    )
                    if item["session_id"] == session_id
                ]
            )

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
                "role_assignments": copy.deepcopy(
                    [
                        item
                        for item in self.role_assignments
                        if item["session_id"] == session_id
                    ]
                ),
                "fact_assignments": copy.deepcopy(
                    [
                        item
                        for item in self.fact_assignments
                        if item["session_id"] == session_id
                    ]
                ),
                "protocol_snapshot": copy.deepcopy(
                    self.protocol_snapshots.get(session_id)
                ),
                "decisions": copy.deepcopy(
                    [item for item in self.decisions if item["session_id"] == session_id]
                ),
                "instrument_responses": copy.deepcopy(
                    [item for item in self.instrument_responses if item["session_id"] == session_id]
                ),
                "shared_artifacts": copy.deepcopy(
                    [
                        item
                        for item in self.shared_artifacts.values()
                        if item["session_id"] == session_id
                    ]
                ),
                "shared_revisions": copy.deepcopy(
                    [
                        item
                        for item in self.shared_revisions
                        if any(
                            artifact["shared_artifact_id"]
                            == item["shared_artifact_id"]
                            and artifact["session_id"] == session_id
                            for artifact in self.shared_artifacts.values()
                        )
                    ]
                ),
                "shared_confirmations": copy.deepcopy(
                    [
                        item
                        for item in self.shared_confirmations
                        if any(
                            revision["revision_id"] == item["revision_id"]
                            and any(
                                artifact["shared_artifact_id"]
                                == revision["shared_artifact_id"]
                                and artifact["session_id"] == session_id
                                for artifact in self.shared_artifacts.values()
                            )
                            for revision in self.shared_revisions
                        )
                    ]
                ),
                "markers": copy.deepcopy(
                    [item for item in self.markers if item["session_id"] == session_id]
                ),
                "replay_plans": copy.deepcopy(
                    [
                        item
                        for item in self.replay_plans
                        if item["session_id"] == session_id
                    ]
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

    def create_task_definition(self, task: dict[str, Any]) -> dict[str, Any]:
        with self.SessionLocal() as db:
            existing = db.scalar(
                select(Study1TaskDefinitionRow).where(
                    Study1TaskDefinitionRow.task_definition_id
                    == task["task_definition_id"],
                    Study1TaskDefinitionRow.task_version == task["task_version"],
                )
            )
            if existing:
                raise Study1ServiceError(
                    "TASK_DEFINITION_EXISTS", "Task definition already exists", 409
                )
            db.add(_task_definition_orm(task))
            for fact in task["facts"]:
                db.add(
                    _task_fact_orm(
                        task["task_definition_id"], task["task_version"], fact
                    )
                )
            db.commit()
            return copy.deepcopy(task)

    def get_task_definition(
        self, task_definition_id: str, task_version: str | None = None
    ) -> dict[str, Any] | None:
        """Resolve an exact version, or the newest definition for legacy callers."""
        with self.SessionLocal() as db:
            query = select(Study1TaskDefinitionRow).where(
                Study1TaskDefinitionRow.task_definition_id == task_definition_id
            )
            if task_version is not None:
                query = query.where(
                    Study1TaskDefinitionRow.task_version == task_version
                )
            row = db.scalar(
                query.order_by(
                    Study1TaskDefinitionRow.created_at.desc(),
                    Study1TaskDefinitionRow.id.desc(),
                )
            )
            if row is None:
                return None
            facts = db.scalars(
                select(Study1TaskFactRow)
                .where(
                    Study1TaskFactRow.task_definition_id == task_definition_id,
                    Study1TaskFactRow.task_version == row.task_version,
                )
                .order_by(Study1TaskFactRow.id.asc())
            ).all()
            return _task_definition_row_dict(row, facts)

    def replace_task_definition(
        self, task_definition_id: str, task: dict[str, Any]
    ) -> dict[str, Any]:
        with self.SessionLocal() as db:
            row = db.scalar(
                select(Study1TaskDefinitionRow)
                .where(
                    Study1TaskDefinitionRow.task_definition_id == task_definition_id,
                    Study1TaskDefinitionRow.task_version == task["task_version"],
                )
                .with_for_update()
            )
            if row is None:
                raise Study1ServiceError(
                    "TASK_DEFINITION_NOT_FOUND", "Task definition not found", 404
                )
            if row.status != "draft":
                raise Study1ServiceError(
                    "TASK_DEFINITION_IMMUTABLE",
                    "Validated task definitions cannot be modified",
                    409,
                )
            row.task_version = task["task_version"]
            row.title = task["title"]
            row.candidate_ids = task["candidate_ids"]
            row.status = task["status"]
            row.content_checksum = task["content_checksum"]
            old_facts = db.scalars(
                select(Study1TaskFactRow).where(
                    Study1TaskFactRow.task_definition_id == task_definition_id,
                    Study1TaskFactRow.task_version == task["task_version"],
                )
            ).all()
            for fact in old_facts:
                db.delete(fact)
            db.flush()
            for fact in task["facts"]:
                db.add(
                    _task_fact_orm(task_definition_id, task["task_version"], fact)
                )
            db.commit()
            return copy.deepcopy(task)

    def set_task_definition_status(
        self,
        task_definition_id: str,
        task_version: str,
        status: str,
        content_checksum: str,
    ) -> dict[str, Any]:
        with self.SessionLocal() as db:
            row = db.scalar(
                select(Study1TaskDefinitionRow)
                .where(
                    Study1TaskDefinitionRow.task_definition_id == task_definition_id,
                    Study1TaskDefinitionRow.task_version == task_version,
                )
                .with_for_update()
            )
            if row is None:
                raise Study1ServiceError(
                    "TASK_DEFINITION_NOT_FOUND", "Task definition not found", 404
                )
            if row.content_checksum != content_checksum:
                raise Study1ServiceError(
                    "TASK_DEFINITION_CHANGED",
                    "Task definition changed before validation completed",
                    409,
                )
            if row.status != status:
                if row.status != "draft":
                    raise Study1ServiceError(
                        "TASK_DEFINITION_IMMUTABLE",
                        "Validated task definitions cannot be modified",
                        409,
                    )
                row.status = status
            facts = db.scalars(
                select(Study1TaskFactRow)
                .where(
                    Study1TaskFactRow.task_definition_id == task_definition_id,
                    Study1TaskFactRow.task_version == task_version,
                )
                .order_by(Study1TaskFactRow.id.asc())
            ).all()
            db.commit()
            return _task_definition_row_dict(row, facts)

    def list_task_definitions(self, status: str | None = None) -> list[dict[str, Any]]:
        with self.SessionLocal() as db:
            query = select(Study1TaskDefinitionRow)
            if status is not None:
                query = query.where(Study1TaskDefinitionRow.status == status)
            rows = db.scalars(
                query.order_by(
                    Study1TaskDefinitionRow.task_definition_id.asc(),
                    Study1TaskDefinitionRow.task_version.asc(),
                )
            ).all()
            values: list[dict[str, Any]] = []
            for row in rows:
                facts = db.scalars(
                    select(Study1TaskFactRow)
                    .where(
                        Study1TaskFactRow.task_definition_id
                        == row.task_definition_id,
                        Study1TaskFactRow.task_version == row.task_version,
                    )
                    .order_by(Study1TaskFactRow.id.asc())
                ).all()
                values.append(_task_definition_row_dict(row, facts))
            return values

    def create_session(
        self,
        snapshot: dict[str, Any],
        invites: list[dict[str, Any]],
        materials: list[dict[str, Any]] | None = None,
        role_assignments: list[dict[str, Any]] | None = None,
        fact_assignments: list[dict[str, Any]] | None = None,
        initial_events: list[dict[str, Any]] | None = None,
        protocol_snapshot: dict[str, Any] | None = None,
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
            for item in role_assignments or []:
                db.add(Study1RoleAssignmentRow(**item))
            for item in fact_assignments or []:
                db.add(Study1FactAssignmentRow(**item))
            for item in initial_events or []:
                db.add(_event_orm(item))
            if protocol_snapshot is not None:
                db.add(
                    Study1ProtocolSnapshotRow(
                        protocol_snapshot_id=protocol_snapshot["protocol_snapshot_id"],
                        session_id=snapshot["session_id"],
                        schema_version=protocol_snapshot.get("schema_version", "2.0"),
                        protocol_mode=protocol_snapshot.get("protocol_mode", "formal_v2"),
                        canonical_config=protocol_snapshot["canonical_config"],
                        checksum=protocol_snapshot["checksum"],
                        frozen=bool(protocol_snapshot.get("frozen", False)),
                        frozen_at=protocol_snapshot.get("frozen_at"),
                        frozen_by=protocol_snapshot.get("frozen_by"),
                        created_at=protocol_snapshot.get("created_at") or utc_now(),
                    )
                )
            db.commit()

    def get_protocol_snapshot(self, session_id: str) -> dict[str, Any] | None:
        with self.SessionLocal() as db:
            row = db.scalar(
                select(Study1ProtocolSnapshotRow).where(
                    Study1ProtocolSnapshotRow.session_id == session_id
                )
            )
            if row is None:
                return None
            return _protocol_snapshot_row_dict(row)

    def update_protocol_snapshot(
        self, session_id: str, protocol_snapshot: dict[str, Any]
    ) -> dict[str, Any]:
        frozen_at = protocol_snapshot.get("frozen_at")
        if isinstance(frozen_at, str):
            frozen_at = datetime.fromisoformat(frozen_at.replace("Z", "+00:00"))
        created_at = protocol_snapshot.get("created_at") or utc_now()
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if session_row is None:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            row = db.scalar(
                select(Study1ProtocolSnapshotRow)
                .where(Study1ProtocolSnapshotRow.session_id == session_id)
                .with_for_update()
            )
            if row is None:
                db.add(
                    Study1ProtocolSnapshotRow(
                        protocol_snapshot_id=protocol_snapshot["protocol_snapshot_id"],
                        session_id=session_id,
                        schema_version=protocol_snapshot.get("schema_version", "2.0"),
                        protocol_mode=protocol_snapshot.get("protocol_mode", "formal_v2"),
                        canonical_config=protocol_snapshot["canonical_config"],
                        checksum=protocol_snapshot["checksum"],
                        frozen=bool(protocol_snapshot.get("frozen", False)),
                        frozen_at=frozen_at,
                        frozen_by=protocol_snapshot.get("frozen_by"),
                        created_at=created_at,
                    )
                )
            else:
                row.canonical_config = protocol_snapshot["canonical_config"]
                row.checksum = protocol_snapshot["checksum"]
                row.frozen = bool(protocol_snapshot.get("frozen", False))
                row.frozen_at = frozen_at
                row.frozen_by = protocol_snapshot.get("frozen_by")
            snapshot = copy.deepcopy(session_row.payload)
            snapshot["experiment_config"] = copy.deepcopy(
                protocol_snapshot["canonical_config"]
            )
            snapshot["configuration_checksum"] = protocol_snapshot["checksum"]
            snapshot["protocol_snapshot_id"] = protocol_snapshot["protocol_snapshot_id"]
            snapshot["protocol_config_frozen"] = bool(protocol_snapshot.get("frozen"))
            session_row.payload = snapshot
            session_row.updated_at = utc_now()
            db.commit()
            return copy.deepcopy(protocol_snapshot)

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
        completion_override: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with self.SessionLocal() as db:
            row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if not row or row.payload.get("experiment_type") != "study1":
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            original_completion = copy.deepcopy((row.payload or {}).get("completion") or {})
            snapshot = copy.deepcopy(row.payload)
            if completion_override is not None:
                snapshot["completion"] = copy.deepcopy(dict(completion_override))
            transition = transition_phase(
                snapshot, target_phase, actor, reason=reason, override=override
            )
            if snapshot["phase"] == Study1Phase.COMPLETED.value:
                snapshot["status"] = "completed"
            if completion_override is not None:
                snapshot["completion"] = original_completion
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

    def create_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        try:
            with self.SessionLocal() as db:
                db.add(Study1DecisionRow(**decision))
                db.commit()
                return copy.deepcopy(decision)
        except IntegrityError as error:
            raise Study1ServiceError(
                "DECISION_ALREADY_SUBMITTED", "Decision already submitted", 409
            ) from error

    def mark_completion(self, session_id: str, key: str) -> None:
        with self.SessionLocal() as db:
            row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if row is None:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            snapshot = copy.deepcopy(row.payload)
            snapshot.setdefault("completion", {})[key] = True
            row.payload = snapshot
            row.updated_at = utc_now()
            db.commit()

    def list_decisions(self, session_id: str) -> list[dict[str, Any]]:
        with self.SessionLocal() as db:
            rows = db.scalars(
                select(Study1DecisionRow)
                .where(Study1DecisionRow.session_id == session_id)
                .order_by(Study1DecisionRow.created_at.asc())
            ).all()
            return [_decision_row_dict(row) for row in rows]

    def create_instrument_response(self, response: dict[str, Any]) -> dict[str, Any]:
        try:
            with self.SessionLocal() as db:
                db.add(Study1InstrumentResponseRow(**response))
                db.commit()
                return copy.deepcopy(response)
        except IntegrityError as error:
            raise Study1ServiceError(
                "INSTRUMENT_ALREADY_SUBMITTED", "Instrument already submitted", 409
            ) from error

    def get_shared_artifact(
        self, session_id: str, kind: str
    ) -> dict[str, Any] | None:
        with self.SessionLocal() as db:
            artifact = db.scalar(
                select(Study1SharedArtifactRow).where(
                    Study1SharedArtifactRow.session_id == session_id,
                    Study1SharedArtifactRow.kind == kind,
                )
            )
            if artifact is None:
                return None
            revisions = db.scalars(
                select(Study1SharedRevisionRow)
                .where(
                    Study1SharedRevisionRow.shared_artifact_id
                    == artifact.shared_artifact_id
                )
                .order_by(Study1SharedRevisionRow.revision_number.asc())
            ).all()
            confirmations = db.scalars(
                select(Study1SharedConfirmationRow).where(
                    Study1SharedConfirmationRow.revision_id.in_(
                        [row.revision_id for row in revisions]
                    )
                )
            ).all() if revisions else []
            return _shared_artifact_projection(
                _shared_artifact_row_dict(artifact),
                [_shared_revision_row_dict(row) for row in revisions],
                [_shared_confirmation_row_dict(row) for row in confirmations],
            )

    def create_shared_revision(
        self,
        session_id: str,
        kind: str,
        parent_revision_id: str | None,
        content: dict[str, Any],
        identity: dict[str, Any],
    ) -> dict[str, Any]:
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if session_row is None:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            artifact = db.scalar(
                select(Study1SharedArtifactRow)
                .where(
                    Study1SharedArtifactRow.session_id == session_id,
                    Study1SharedArtifactRow.kind == kind,
                )
                .with_for_update()
            )
            now = utc_now()
            if artifact is None:
                if parent_revision_id is not None:
                    raise Study1ServiceError(
                        "SHARED_REVISION_CONFLICT",
                        "parent_revision_id does not match the current revision",
                        409,
                    )
                artifact = Study1SharedArtifactRow(
                    shared_artifact_id=str(uuid.uuid4()),
                    session_id=session_id,
                    kind=kind,
                    current_revision_id=None,
                    locked_revision_id=None,
                    locked_at=None,
                    created_at=now,
                )
                db.add(artifact)
                db.flush()
            if artifact.locked_revision_id:
                raise Study1ServiceError(
                    "SHARED_ARTIFACT_LOCKED", "Shared artifact is already locked", 409
                )
            if parent_revision_id != artifact.current_revision_id:
                raise Study1ServiceError(
                    "SHARED_REVISION_CONFLICT",
                    "parent_revision_id does not match the current revision",
                    409,
                )
            revision_number = (
                db.scalar(
                    select(Study1SharedRevisionRow.revision_number)
                    .where(
                        Study1SharedRevisionRow.shared_artifact_id
                        == artifact.shared_artifact_id
                    )
                    .order_by(Study1SharedRevisionRow.revision_number.desc())
                    .limit(1)
                )
                or 0
            ) + 1
            revision = Study1SharedRevisionRow(
                revision_id=str(uuid.uuid4()),
                shared_artifact_id=artifact.shared_artifact_id,
                revision_number=revision_number,
                parent_revision_id=parent_revision_id,
                content=copy.deepcopy(content),
                content_checksum=content_checksum(content),
                editor_participant_id=identity["participant_id"],
                editor_role=identity["role"],
                created_at=now,
            )
            db.add(revision)
            artifact.current_revision_id = revision.revision_id
            event = _shared_artifact_event(
                session_row.payload,
                identity,
                "shared_revision_created",
                {
                    "kind": kind,
                    "revision_id": revision.revision_id,
                    "revision_number": revision_number,
                    "parent_revision_id": parent_revision_id,
                    "content_checksum": revision.content_checksum,
                },
                now,
            )
            db.add(_event_orm(event))
            db.commit()
            return _shared_revision_projection(
                _shared_revision_row_dict(revision), [], _shared_artifact_row_dict(artifact)
            )

    def confirm_shared_revision(
        self,
        session_id: str,
        kind: str,
        revision_id: str,
        identity: dict[str, Any],
    ) -> dict[str, Any]:
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow)
                .where(ResearchSessionRow.session_id == session_id)
                .with_for_update()
            )
            if session_row is None:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            artifact = db.scalar(
                select(Study1SharedArtifactRow)
                .where(
                    Study1SharedArtifactRow.session_id == session_id,
                    Study1SharedArtifactRow.kind == kind,
                )
                .with_for_update()
            )
            if artifact is None or artifact.current_revision_id != revision_id:
                raise Study1ServiceError(
                    "SHARED_REVISION_NOT_CURRENT",
                    "Only the current revision can be confirmed",
                    409,
                )
            revision = db.scalar(
                select(Study1SharedRevisionRow).where(
                    Study1SharedRevisionRow.revision_id == revision_id
                )
            )
            if revision is None:
                raise Study1ServiceError(
                    "SHARED_REVISION_NOT_FOUND", "Shared revision not found", 404
                )
            existing = db.scalar(
                select(Study1SharedConfirmationRow).where(
                    Study1SharedConfirmationRow.revision_id == revision_id,
                    Study1SharedConfirmationRow.participant_id
                    == identity["participant_id"],
                )
            )
            now = utc_now()
            if existing is None:
                db.add(
                    Study1SharedConfirmationRow(
                        confirmation_id=str(uuid.uuid4()),
                        revision_id=revision_id,
                        participant_id=identity["participant_id"],
                        role=identity["role"],
                        confirmed_at=now,
                    )
                )
                db.add(
                    _event_orm(
                        _shared_artifact_event(
                            session_row.payload,
                            identity,
                            "shared_revision_confirmed",
                            {"kind": kind, "revision_id": revision_id},
                            now,
                        )
                    )
                )
                db.flush()
            confirmations = db.scalars(
                select(Study1SharedConfirmationRow).where(
                    Study1SharedConfirmationRow.revision_id == revision_id
                )
            ).all()
            roles = {row.role for row in confirmations}
            if roles == {role.value for role in HUMAN_ROLES} and not artifact.locked_revision_id:
                artifact.locked_revision_id = revision_id
                artifact.locked_at = now
                snapshot = copy.deepcopy(session_row.payload)
                _apply_shared_lock_to_snapshot(snapshot, kind)
                session_row.payload = snapshot
                if kind == SharedArtifactKind.TEAM_FINAL.value:
                    existing_team_decision = db.scalar(
                        select(Study1DecisionRow).where(
                            Study1DecisionRow.session_id == session_id,
                            Study1DecisionRow.decision_kind == SharedArtifactKind.TEAM_FINAL.value,
                        )
                    )
                    if existing_team_decision is None:
                        db.add(_team_final_decision_orm(session_id, revision, now))
                db.add(
                    _event_orm(
                        _shared_artifact_event(
                            snapshot,
                            identity,
                            "shared_artifact_locked",
                            {"kind": kind, "revision_id": revision_id},
                            now,
                        )
                    )
                )
            db.commit()
            return _shared_revision_projection(
                _shared_revision_row_dict(revision),
                [_shared_confirmation_row_dict(row) for row in confirmations],
                _shared_artifact_row_dict(artifact),
            )

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
            if event_type == "rtc_metric_sample":
                _validate_rtc_telemetry_access(snapshot, identity)
            else:
                _validate_review_access(snapshot, identity)
            event = _record_review_ui_event(
                snapshot, identity, event_type, payload, utc_now()
            )
            db.add(_event_orm(event))
            session_row.payload = snapshot
            session_row.updated_at = utc_now()
            db.commit()
            return event

    def record_review_event_batch(
        self,
        session_id: str,
        identity: dict[str, Any],
        visit_id: str,
        events: list[dict[str, Any]],
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
            result = _record_review_event_batch(
                snapshot, identity, visit_id, events, utc_now()
            )
            db.add(_event_orm(result["event"]))
            session_row.payload = snapshot
            session_row.updated_at = utc_now()
            db.commit()
            return result["response"]

    def create_marker(
        self,
        session_id: str,
        actor: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow).where(
                    ResearchSessionRow.session_id == session_id
                )
            )
            if not session_row or session_row.payload.get("experiment_type") != "study1":
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            marker = normalize_marker(
                session_id=session_id,
                actor=actor,
                payload=payload,
                created_at=utc_now(),
            )
            db.add(
                Study1MarkerRow(
                    marker_id=marker["marker_id"],
                    session_id=marker["session_id"],
                    marker_type=marker["marker_type"],
                    source=marker["source"],
                    participant_id=marker["participant_id"],
                    role=marker["role"],
                    participant_visible=marker["participant_visible"],
                    start_ms=marker["start_ms"],
                    end_ms=marker["end_ms"],
                    segment_ids=marker["segment_ids"],
                    recording_ids=marker["recording_ids"],
                    reason=marker["reason"],
                    created_at=marker["created_at"],
                    marker_metadata=marker["metadata"],
                )
            )
            db.add(_event_orm(_marker_event(session_row.payload, actor, marker)))
            db.commit()
            return marker

    def list_markers(
        self, session_id: str, actor: dict[str, Any]
    ) -> list[dict[str, Any]]:
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow).where(
                    ResearchSessionRow.session_id == session_id
                )
            )
            if not session_row or session_row.payload.get("experiment_type") != "study1":
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            rows = db.scalars(
                select(Study1MarkerRow)
                .where(Study1MarkerRow.session_id == session_id)
                .order_by(Study1MarkerRow.start_ms.asc(), Study1MarkerRow.created_at.asc())
            ).all()
            return [
                marker
                for marker in (_marker_row_dict(row) for row in rows)
                if marker_visible_to_actor(marker, actor)
            ]

    def create_replay_plan(
        self,
        session_id: str,
        actor: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow).where(
                    ResearchSessionRow.session_id == session_id
                )
            )
            if not session_row or session_row.payload.get("experiment_type") != "study1":
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            marker_ids = _normalize_optional_string_set(payload.get("marker_ids"))
            marker_query = select(Study1MarkerRow).where(
                Study1MarkerRow.session_id == session_id
            )
            if marker_ids:
                marker_query = marker_query.where(
                    Study1MarkerRow.marker_id.in_(marker_ids)
                )
            marker_rows = db.scalars(
                marker_query.order_by(
                    Study1MarkerRow.start_ms.asc(), Study1MarkerRow.created_at.asc()
                )
            ).all()
            existing_count = len(
                db.scalars(
                    select(Study1ReplayPlanRow.replay_plan_id).where(
                        Study1ReplayPlanRow.session_id == session_id
                    )
                ).all()
            )
            plan = build_replay_plan(
                session_id=session_id,
                markers=[_marker_row_dict(row) for row in marker_rows],
                existing_count=existing_count,
                created_by=str(actor.get("participant_id") or actor.get("role") or ""),
                context_seconds=int(payload.get("context_seconds", 10)),
                created_at=utc_now(),
            )
            db.add(
                Study1ReplayPlanRow(
                    replay_plan_id=plan["replay_plan_id"],
                    session_id=session_id,
                    version=plan["version"],
                    context_seconds=plan["context_seconds"],
                    source_marker_ids=plan["source_marker_ids"],
                    items=plan["items"],
                    created_by=plan["created_by"],
                    created_at=plan["created_at"],
                    generator_version=plan["generator_version"],
                    replay_metadata=plan["metadata"],
                )
            )
            db.add(_event_orm(_replay_plan_event(session_row.payload, actor, plan)))
            db.commit()
            return plan

    def list_replay_plans(
        self, session_id: str, actor: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if actor.get("role") != Study1Role.RESEARCHER.value:
            raise Study1ServiceError("FORBIDDEN", "Researcher role required", 403)
        with self.SessionLocal() as db:
            session_row = db.scalar(
                select(ResearchSessionRow).where(
                    ResearchSessionRow.session_id == session_id
                )
            )
            if not session_row or session_row.payload.get("experiment_type") != "study1":
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            rows = db.scalars(
                select(Study1ReplayPlanRow)
                .where(Study1ReplayPlanRow.session_id == session_id)
                .order_by(Study1ReplayPlanRow.created_at.asc())
            ).all()
            return [_replay_plan_row_dict(row) for row in rows]

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
            role_assignment_rows = db.scalars(
                select(Study1RoleAssignmentRow)
                .where(Study1RoleAssignmentRow.session_id == session_id)
                .order_by(Study1RoleAssignmentRow.assignment_order.asc())
            ).all()
            fact_assignment_rows = db.scalars(
                select(Study1FactAssignmentRow)
                .where(Study1FactAssignmentRow.session_id == session_id)
                .order_by(Study1FactAssignmentRow.id.asc())
            ).all()
            decision_rows = db.scalars(
                select(Study1DecisionRow)
                .where(Study1DecisionRow.session_id == session_id)
                .order_by(Study1DecisionRow.created_at.asc())
            ).all()
            instrument_response_rows = db.scalars(
                select(Study1InstrumentResponseRow)
                .where(Study1InstrumentResponseRow.session_id == session_id)
                .order_by(Study1InstrumentResponseRow.submitted_at.asc())
            ).all()
            shared_artifact_rows = db.scalars(
                select(Study1SharedArtifactRow)
                .where(Study1SharedArtifactRow.session_id == session_id)
                .order_by(Study1SharedArtifactRow.created_at.asc())
            ).all()
            shared_artifact_ids = [
                row.shared_artifact_id for row in shared_artifact_rows
            ]
            shared_revision_rows = db.scalars(
                select(Study1SharedRevisionRow)
                .where(
                    Study1SharedRevisionRow.shared_artifact_id.in_(
                        shared_artifact_ids
                    )
                )
                .order_by(
                    Study1SharedRevisionRow.shared_artifact_id.asc(),
                    Study1SharedRevisionRow.revision_number.asc(),
                )
            ).all() if shared_artifact_ids else []
            shared_revision_ids = [row.revision_id for row in shared_revision_rows]
            shared_confirmation_rows = db.scalars(
                select(Study1SharedConfirmationRow)
                .where(
                    Study1SharedConfirmationRow.revision_id.in_(
                        shared_revision_ids
                    )
                )
                .order_by(Study1SharedConfirmationRow.confirmed_at.asc())
            ).all() if shared_revision_ids else []
            marker_rows = db.scalars(
                select(Study1MarkerRow)
                .where(Study1MarkerRow.session_id == session_id)
                .order_by(Study1MarkerRow.start_ms.asc(), Study1MarkerRow.created_at.asc())
            ).all()
            replay_plan_rows = db.scalars(
                select(Study1ReplayPlanRow)
                .where(Study1ReplayPlanRow.session_id == session_id)
                .order_by(Study1ReplayPlanRow.created_at.asc())
            ).all()
            protocol_row = db.scalar(
                select(Study1ProtocolSnapshotRow).where(
                    Study1ProtocolSnapshotRow.session_id == session_id
                )
            )
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
                "role_assignments": [
                    _role_assignment_row_dict(row) for row in role_assignment_rows
                ],
                "fact_assignments": [
                    _fact_assignment_row_dict(row) for row in fact_assignment_rows
                ],
                "protocol_snapshot": (
                    _protocol_snapshot_row_dict(protocol_row)
                    if protocol_row is not None
                    else None
                ),
                "decisions": [_decision_row_dict(row) for row in decision_rows],
                "instrument_responses": [
                    _instrument_response_row_dict(row)
                    for row in instrument_response_rows
                ],
                "shared_artifacts": [
                    _shared_artifact_row_dict(row) for row in shared_artifact_rows
                ],
                "shared_revisions": [
                    _shared_revision_row_dict(row) for row in shared_revision_rows
                ],
                "shared_confirmations": [
                    _shared_confirmation_row_dict(row)
                    for row in shared_confirmation_rows
                ],
                "markers": [_marker_row_dict(row) for row in marker_rows],
                "replay_plans": [
                    _replay_plan_row_dict(row) for row in replay_plan_rows
                ],
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
            expires_at = row.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= used_at:
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


def _task_definition_orm(task: dict[str, Any]) -> Study1TaskDefinitionRow:
    return Study1TaskDefinitionRow(
        task_definition_id=task["task_definition_id"],
        task_version=task["task_version"],
        title=task["title"],
        candidate_ids=copy.deepcopy(task["candidate_ids"]),
        status=task["status"],
        content_checksum=task["content_checksum"],
        created_at=task["created_at"],
        created_by=task["created_by"],
    )


def _task_fact_orm(
    task_definition_id: str,
    task_version: str,
    fact: dict[str, Any],
) -> Study1TaskFactRow:
    return Study1TaskFactRow(
        task_definition_id=task_definition_id,
        task_version=task_version,
        fact_id=fact["fact_id"],
        candidate_id=fact["candidate_id"],
        text=fact["text"],
        valence=fact["valence"],
        information_type=fact["information_type"],
        visible_to_roles=copy.deepcopy(fact["visible_to_roles"]),
    )


def _task_definition_row_dict(
    row: Study1TaskDefinitionRow, facts: list[Study1TaskFactRow]
) -> dict[str, Any]:
    return {
        "task_definition_id": row.task_definition_id,
        "task_version": row.task_version,
        "title": row.title,
        "candidate_ids": list(row.candidate_ids or []),
        "facts": [
            {
                "fact_id": fact.fact_id,
                "candidate_id": fact.candidate_id,
                "text": fact.text,
                "valence": fact.valence,
                "information_type": fact.information_type,
                "visible_to_roles": list(fact.visible_to_roles or []),
            }
            for fact in facts
        ],
        "status": row.status,
        "content_checksum": row.content_checksum,
        "created_at": row.created_at,
        "created_by": row.created_by,
    }


def _role_assignment_row_dict(row: Study1RoleAssignmentRow) -> dict[str, Any]:
    return {
        "assignment_id": row.assignment_id,
        "session_id": row.session_id,
        "participant_slot_id": row.participant_slot_id,
        "participant_id": row.participant_id,
        "role": row.role,
        "assignment_order": row.assignment_order,
        "randomization_seed": row.randomization_seed,
        "assigned_at": row.assigned_at,
    }


def _fact_assignment_row_dict(row: Study1FactAssignmentRow) -> dict[str, Any]:
    return {
        "assignment_id": row.assignment_id,
        "session_id": row.session_id,
        "task_definition_id": row.task_definition_id,
        "task_version": row.task_version,
        "fact_id": row.fact_id,
        "role": row.role,
        "assigned_at": row.assigned_at,
    }


def _protocol_snapshot_row_dict(row: Study1ProtocolSnapshotRow) -> dict[str, Any]:
    return {
        "protocol_snapshot_id": row.protocol_snapshot_id,
        "session_id": row.session_id,
        "schema_version": row.schema_version,
        "protocol_mode": row.protocol_mode,
        "canonical_config": copy.deepcopy(row.canonical_config),
        "checksum": row.checksum,
        "frozen": bool(row.frozen),
        "frozen_at": utc_iso(row.frozen_at) if row.frozen_at else None,
        "frozen_by": row.frozen_by,
        "created_at": utc_iso(row.created_at) if row.created_at else None,
    }


def _decision_row_dict(row: Study1DecisionRow) -> dict[str, Any]:
    return {
        "decision_id": row.decision_id,
        "session_id": row.session_id,
        "decision_kind": row.decision_kind,
        "participant_id": row.participant_id,
        "role": row.role,
        "candidate_id": row.candidate_id,
        "rationale": row.rationale,
        "confidence": row.confidence,
        "ratings": dict(row.ratings or {}),
        "decision_status": row.decision_status,
        "phase": row.phase,
        "instrument_version": row.instrument_version,
        "source_revision_id": row.source_revision_id,
        "locked": bool(row.locked),
        "created_at": utc_iso(row.created_at) if row.created_at else None,
    }


def _shared_artifact_event(
    session: Mapping[str, Any],
    identity: Mapping[str, Any],
    event_type: str,
    payload: dict[str, Any],
    occurred_at: datetime,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "participant_id": identity.get("participant_id"),
        "role": identity.get("role"),
        "phase": session.get("phase"),
        "phase_version": int(session.get("phase_version") or 1),
        "event_type": event_type,
        "occurred_at": occurred_at,
        "payload": copy.deepcopy(payload),
        "idempotency_key": None,
    }


def _apply_shared_lock_to_snapshot(session: MutableMapping[str, Any], kind: str) -> None:
    completion = session.setdefault("completion", {})
    if kind == SharedArtifactKind.TEAM_FINAL.value:
        completion["team_final_locked"] = True
    elif kind == SharedArtifactKind.FOLLOWUP_TASK.value:
        completion["followup_task_locked"] = True
        for role in HUMAN_ROLES:
            completion[f"followup_task:{role.value}"] = True


def _team_final_decision(
    session_id: str, revision: Mapping[str, Any], created_at: datetime
) -> dict[str, Any]:
    content = revision["content"]
    return {
        "decision_id": str(uuid.uuid4()),
        "session_id": session_id,
        "decision_kind": SharedArtifactKind.TEAM_FINAL.value,
        "participant_id": None,
        "role": "team",
        "candidate_id": content["candidate_id"],
        "rationale": content["rationale"],
        "confidence": content.get("confidence"),
        "ratings": copy.deepcopy(content.get("ratings") or {}),
        "decision_status": content.get("decision_status"),
        "phase": Study1Phase.FINAL_DECISION.value,
        "instrument_version": "2.0",
        "source_revision_id": revision["revision_id"],
        "locked": True,
        "created_at": created_at,
    }


def _team_final_decision_orm(
    session_id: str, revision: Study1SharedRevisionRow, created_at: datetime
) -> Study1DecisionRow:
    content = revision.content
    return Study1DecisionRow(
        decision_id=str(uuid.uuid4()),
        session_id=session_id,
        decision_kind=SharedArtifactKind.TEAM_FINAL.value,
        participant_id=None,
        role="team",
        candidate_id=content["candidate_id"],
        rationale=content["rationale"],
        confidence=content.get("confidence"),
        ratings=copy.deepcopy(content.get("ratings") or {}),
        decision_status=content.get("decision_status"),
        phase=Study1Phase.FINAL_DECISION.value,
        instrument_version="2.0",
        source_revision_id=revision.revision_id,
        locked=True,
        created_at=created_at,
    )


def _shared_revision_projection(
    revision: Mapping[str, Any],
    confirmations: list[Mapping[str, Any]],
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    roles = {str(item.get("role") or "") for item in confirmations}
    ordered_roles = [role.value for role in HUMAN_ROLES]
    return {
        "revision_id": revision["revision_id"],
        "shared_artifact_id": revision["shared_artifact_id"],
        "kind": artifact["kind"],
        "revision_number": revision["revision_number"],
        "parent_revision_id": revision.get("parent_revision_id"),
        "content": copy.deepcopy(revision["content"]),
        "content_checksum": revision["content_checksum"],
        "editor_participant_id": revision["editor_participant_id"],
        "editor_role": revision["editor_role"],
        "created_at": utc_iso(revision["created_at"]),
        "confirmed_roles": [role for role in ordered_roles if role in roles],
        "locked": artifact.get("locked_revision_id") == revision["revision_id"],
    }


def _shared_artifact_projection(
    artifact: Mapping[str, Any],
    revisions: list[Mapping[str, Any]],
    confirmations: list[Mapping[str, Any]],
) -> dict[str, Any]:
    current_id = artifact.get("current_revision_id")
    current = next(
        (item for item in revisions if item["revision_id"] == current_id), None
    )
    current_confirmations = [
        item for item in confirmations if item["revision_id"] == current_id
    ]
    return {
        "shared_artifact_id": artifact["shared_artifact_id"],
        "session_id": artifact["session_id"],
        "kind": artifact["kind"],
        "current_revision_id": current_id,
        "locked_revision_id": artifact.get("locked_revision_id"),
        "locked_at": (
            utc_iso(artifact["locked_at"]) if artifact.get("locked_at") else None
        ),
        "current_revision": (
            _shared_revision_projection(current, current_confirmations, artifact)
            if current is not None
            else None
        ),
        "locked": bool(artifact.get("locked_revision_id")),
    }


def _shared_artifact_row_dict(row: Study1SharedArtifactRow) -> dict[str, Any]:
    return {
        "shared_artifact_id": row.shared_artifact_id,
        "session_id": row.session_id,
        "kind": row.kind,
        "current_revision_id": row.current_revision_id,
        "locked_revision_id": row.locked_revision_id,
        "locked_at": row.locked_at,
        "created_at": row.created_at,
    }


def _shared_revision_row_dict(row: Study1SharedRevisionRow) -> dict[str, Any]:
    return {
        "revision_id": row.revision_id,
        "shared_artifact_id": row.shared_artifact_id,
        "revision_number": row.revision_number,
        "parent_revision_id": row.parent_revision_id,
        "content": copy.deepcopy(row.content),
        "content_checksum": row.content_checksum,
        "editor_participant_id": row.editor_participant_id,
        "editor_role": row.editor_role,
        "created_at": row.created_at,
    }


def _shared_confirmation_row_dict(
    row: Study1SharedConfirmationRow,
) -> dict[str, Any]:
    return {
        "confirmation_id": row.confirmation_id,
        "revision_id": row.revision_id,
        "participant_id": row.participant_id,
        "role": row.role,
        "confirmed_at": row.confirmed_at,
    }


def _instrument_response_row_dict(row: Study1InstrumentResponseRow) -> dict[str, Any]:
    return {
        "response_id": row.response_id,
        "session_id": row.session_id,
        "participant_id": row.participant_id,
        "role": row.role,
        "instrument_definition_id": row.instrument_definition_id,
        "instrument_version": row.instrument_version,
        "phase": row.phase,
        "ordered_responses": copy.deepcopy(row.ordered_responses),
        "response_checksum": row.response_checksum,
        "submitted_at": utc_iso(row.submitted_at) if row.submitted_at else None,
    }


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


def _marker_row_dict(row: Study1MarkerRow) -> dict[str, Any]:
    return {
        "marker_id": row.marker_id,
        "session_id": row.session_id,
        "marker_type": row.marker_type,
        "type": row.marker_type,
        "source": row.source,
        "participant_id": row.participant_id,
        "role": row.role,
        "participant_visible": bool(row.participant_visible),
        "start_ms": row.start_ms,
        "end_ms": row.end_ms,
        "segment_ids": list(row.segment_ids or []),
        "recording_ids": list(row.recording_ids or []),
        "reason": row.reason,
        "created_at": utc_iso(row.created_at),
        "metadata": dict(row.marker_metadata or {}),
    }


def _replay_plan_row_dict(row: Study1ReplayPlanRow) -> dict[str, Any]:
    return {
        "replay_plan_id": row.replay_plan_id,
        "session_id": row.session_id,
        "version": row.version,
        "context_seconds": row.context_seconds,
        "source_marker_ids": list(row.source_marker_ids or []),
        "items": copy.deepcopy(row.items or []),
        "created_by": row.created_by,
        "created_at": utc_iso(row.created_at),
        "generator_version": row.generator_version,
        "metadata": dict(row.replay_metadata or {}),
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


def _validate_rtc_telemetry_access(
    session: dict[str, Any] | None, identity: dict[str, Any]
) -> None:
    if not session:
        raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
    if identity.get("role") not in {
        Study1Role.PRINCIPAL.value,
        Study1Role.TEAMMATE_1.value,
        Study1Role.TEAMMATE_2.value,
    }:
        raise Study1ServiceError(
            "RTC_TELEMETRY_FORBIDDEN", "Participant role required", 403
        )
    if session.get("status") in {"terminated", "completed"}:
        raise Study1ServiceError("SESSION_NOT_ACTIVE", "Session is not active", 409)


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
    if event_type == "critical_marker":
        safe_payload = {
            "target_type": str(safe_payload.get("target_type") or "")[:32],
            "target_id": str(safe_payload.get("target_id") or "")[:128],
            "note": str(safe_payload.get("note") or "")[:500],
        }
    if event_type == "recording_replay":
        safe_payload = {
            "recording_id": str(safe_payload.get("recording_id") or "")[:160],
            "action": str(safe_payload.get("action") or "")[:32],
        }
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


def _record_review_event_batch(
    session: dict[str, Any],
    identity: dict[str, Any],
    visit_id: str,
    events: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    state = session.setdefault("review_telemetry", {})
    accumulator = ReviewTelemetryAccumulator(state)
    summary = accumulator.record_batch(
        {
            "visit_id": visit_id,
            "session_id": session["session_id"],
            "participant_id": identity["participant_id"],
            "role": identity["role"],
        },
        events if isinstance(events, list) else [],
        received_at_ms=int(now.timestamp() * 1000),
    )
    session["completion"]["review_reading_recorded:principal"] = True
    minimum = int(session.get("minimum_review_seconds") or 0)
    if summary.active_seconds >= minimum:
        session["completion"]["minimum_review_time_met:principal"] = True
    response = {
        "accepted": True,
        "summary": summary.public_dict(),
    }
    event = _ui_event(
        session,
        identity,
        "review_telemetry_batch",
        {
            "visit_id": visit_id,
            "accepted_event_count": summary.event_count,
            "duplicate_event_count": summary.duplicate_count,
            "summary": summary.public_dict(),
        },
        now,
    )
    return {"response": response, "event": event}


def _normalize_optional_string_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list):
        raise ReplayValidationError(
            "INVALID_REPLAY_MARKERS", "marker_ids must be a list"
        )
    return {item for item in (str(item).strip() for item in value) if item}


def _marker_event(
    session: dict[str, Any],
    actor: dict[str, Any],
    marker: dict[str, Any],
) -> dict[str, Any]:
    return _status_event(
        session,
        actor,
        "marker_created",
        {
            "marker_id": marker["marker_id"],
            "marker_type": marker["marker_type"],
            "source": marker["source"],
            "participant_visible": marker["participant_visible"],
            "start_ms": marker["start_ms"],
            "end_ms": marker["end_ms"],
            "segment_ids": list(marker.get("segment_ids") or []),
            "recording_ids": list(marker.get("recording_ids") or []),
        },
    )


def _replay_plan_event(
    session: dict[str, Any],
    actor: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    return _status_event(
        session,
        actor,
        "replay_plan_created",
        {
            "replay_plan_id": plan["replay_plan_id"],
            "version": plan["version"],
            "context_seconds": plan["context_seconds"],
            "source_marker_ids": list(plan.get("source_marker_ids") or []),
            "item_count": len(plan.get("items") or []),
            "generator_version": plan["generator_version"],
        },
    )


def _review_payload(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    latest: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        latest[artifact["type"]] = artifact
    return {
        "summary": latest.get("summary"),
        "transcript": latest.get("transcript"),
        "recording_manifest": latest.get("recording_manifest"),
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
    reason = str(payload.get("reason") or "").strip()
    if (
        session.get("structured_instruments")
        and action in {"pause", "resume", "extend", "terminate"}
        and not reason
    ):
        raise Study1ServiceError(
            "CONTROL_REASON_REQUIRED",
            f"A reason is required for {action} in a locked Study 1 session",
            400,
        )
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
        session["remaining_seconds"] = _remaining_seconds(session)
        session["phase_deadline_at"] = None
        session["status"] = "paused"
        events.append(_status_event(session, actor, "session_pause", {"reason": reason or None}))
    elif action == "resume":
        if status != "paused":
            raise Study1ServiceError(
                "SESSION_CANNOT_RESUME", "Only a paused session can be resumed", 409
            )
        session["status"] = "running"
        remaining = int(session.get("remaining_seconds") or 0)
        session["phase_deadline_at"] = (
            utc_iso(utc_now() + timedelta(seconds=remaining)) if remaining > 0 else None
        )
        events.append(_status_event(session, actor, "session_resume", {"reason": reason or None}))
    elif action == "extend":
        seconds = int(payload.get("seconds") or 0)
        if seconds <= 0 or seconds > 86400:
            raise Study1ServiceError(
                "INVALID_EXTENSION", "seconds must be between 1 and 86400", 400
            )
        session["remaining_seconds"] = _remaining_seconds(session) + seconds
        if session["status"] == "running":
            session["phase_deadline_at"] = utc_iso(
                utc_now() + timedelta(seconds=session["remaining_seconds"])
            )
        events.append(
            _status_event(
                session,
                actor,
                "session_extend",
                {
                    "seconds": seconds,
                    "remaining_seconds": session["remaining_seconds"],
                    "reason": reason or None,
                },
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
                {"reason": reason or None},
            )
        )
    else:
        raise Study1ServiceError("UNKNOWN_CONTROL_ACTION", "Unknown control action", 400)
    return events


def _remaining_seconds(session: dict[str, Any]) -> int:
    deadline = session.get("phase_deadline_at")
    if deadline and session.get("status") == "running":
        try:
            deadline_at = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
            return max(0, math.ceil((deadline_at - utc_now()).total_seconds()))
        except ValueError:
            pass
    return max(0, int(session.get("remaining_seconds") or 0))


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
    try:
        definition = incident_definition(category)
    except IncidentCodeError as error:
        raise Study1ServiceError(error.code, str(error), 400) from error
    allowed_severity = {"info", "warning", "critical"}
    if severity not in allowed_severity:
        raise Study1ServiceError("INVALID_INCIDENT_SEVERITY", "Invalid severity", 400)
    enriched_metadata = copy.deepcopy(metadata or {})
    enriched_metadata.setdefault("incident_label", definition.label)
    enriched_metadata.setdefault("incident_component", definition.component)
    return {
        "incident_id": str(uuid.uuid4()),
        "session_id": session_id,
        "category": definition.code,
        "severity": severity,
        "description": clean_description,
        "created_at": utc_now(),
        "created_by": actor.get("participant_id") or "researcher",
        "metadata": enriched_metadata,
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
    state = formal_readiness(session) if session.get("protocol_mode") == "formal_v2" else readiness(session)
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
        "remaining_seconds": _remaining_seconds(session),
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
        self.media_gateway = media_gateway or create_media_gateway_from_env()

    @staticmethod
    def _authorize(session: dict[str, Any], action: str, role: str | None = None) -> None:
        # Legacy Sessions retain their original behavior; formal Sessions use
        # the canonical policy so every runtime entry point sees the same gate.
        if session.get("protocol_mode") != "formal_v2":
            return
        try:
            authorize_action(session, action, role)
        except ActionPolicyViolation as error:
            raise Study1ServiceError(error.code, str(error), error.status) from error

    def create_task_definition(
        self, actor: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        self._require_researcher(actor)
        canonical = self._validate_task_payload(payload)
        task = {
            **canonical,
            "status": "draft",
            "created_at": utc_now(),
            "created_by": str(actor.get("participant_id") or "researcher"),
        }
        return self.repository.create_task_definition(task)

    def replace_task_definition(
        self,
        task_definition_id: str,
        actor: dict[str, Any],
        payload: dict[str, Any],
        task_version: str | None = None,
    ) -> dict[str, Any]:
        self._require_researcher(actor)
        replacement = copy.deepcopy(payload)
        replacement["task_definition_id"] = task_definition_id
        if task_version is not None:
            clean_route_version = str(task_version).strip()
            payload_version = str(replacement.get("task_version") or "").strip()
            if payload_version and payload_version != clean_route_version:
                raise Study1ServiceError(
                    "TASK_VERSION_MISMATCH",
                    "Payload task_version does not match the selected version",
                    400,
                )
            replacement["task_version"] = clean_route_version
        selected_version = str(replacement.get("task_version") or "").strip() or None
        existing = self.repository.get_task_definition(
            task_definition_id, selected_version
        )
        if existing is None:
            raise Study1ServiceError(
                "TASK_DEFINITION_NOT_FOUND", "Task definition not found", 404
            )
        if existing["status"] == "validated":
            raise Study1ServiceError(
                "TASK_DEFINITION_IMMUTABLE",
                "Validated task definitions cannot be modified",
                409,
            )
        canonical = self._validate_task_payload(replacement)
        task = {
            **canonical,
            "status": "draft",
            "created_at": existing["created_at"],
            "created_by": existing["created_by"],
        }
        return self.repository.replace_task_definition(task_definition_id, task)

    def validate_task_definition(
        self,
        task_definition_id: str,
        actor: dict[str, Any],
        task_version: str | None = None,
    ) -> dict[str, Any]:
        self._require_researcher(actor)
        task = self.repository.get_task_definition(task_definition_id, task_version)
        if task is None:
            raise Study1ServiceError(
                "TASK_DEFINITION_NOT_FOUND", "Task definition not found", 404
            )
        if task["status"] == "validated":
            return task
        canonical = self._validate_task_payload(task)
        return self.repository.set_task_definition_status(
            task_definition_id,
            task["task_version"],
            "validated",
            canonical["content_checksum"],
        )

    def list_task_definitions(
        self, status: str | None = None
    ) -> list[dict[str, Any]]:
        clean_status = str(status).strip() if status is not None else None
        if clean_status not in (None, "draft", "validated"):
            raise Study1ServiceError(
                "INVALID_TASK_STATUS", "status must be draft or validated", 400
            )
        return self.repository.list_task_definitions(clean_status)

    def get_task_definition(
        self, task_definition_id: str, task_version: str | None = None
    ) -> dict[str, Any]:
        task = self.repository.get_task_definition(task_definition_id, task_version)
        if task is None:
            raise Study1ServiceError(
                "TASK_DEFINITION_NOT_FOUND", "Task definition not found", 404
            )
        return task

    @staticmethod
    def _require_researcher(actor: dict[str, Any]) -> None:
        if actor.get("role") != Study1Role.RESEARCHER.value:
            raise Study1ServiceError("FORBIDDEN", "Researcher role required", 403)

    @staticmethod
    def _validate_task_payload(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return validate_registered_task(payload)
        except TaskDefinitionValidationError as error:
            raise Study1ServiceError(error.code, str(error), 400) from error

    def create_session(
        self,
        session_name: str,
        invite_ttl_seconds: int = 86400,
        materials_by_role: dict[str, list[dict[str, Any]]] | None = None,
        minimum_review_seconds: int = 0,
        experiment_config: dict[str, Any] | None = None,
        task_definition_id: str | None = None,
    ) -> dict[str, Any]:
        clean_name = (session_name or "").strip()
        if not clean_name:
            raise Study1ServiceError(
                "SESSION_NAME_REQUIRED", "session_name is required", 400
            )
        registered_task: dict[str, Any] | None = None
        raw_config = copy.deepcopy(experiment_config or {})
        if task_definition_id is not None:
            clean_task_id = str(task_definition_id).strip()
            requested_version = (
                str(raw_config.get("task_version") or "").strip() or None
            )
            registered_task = self.repository.get_task_definition(
                clean_task_id, requested_version
            )
            if registered_task is None or registered_task.get("status") != "validated":
                raise Study1ServiceError(
                    "TASK_NOT_VALIDATED",
                    "Formal sessions require a validated task definition",
                    409,
                )
            raw_config.setdefault("role_assignment_mode", "randomized")
            raw_config["task_version"] = registered_task["task_version"]
            raw_config["task_instance_id"] = registered_task["task_definition_id"]
        if registered_task:
            # Formal Sessions always use the complete V2 vocabulary.  Request
            # values override explicit defaults, while every phase/provider/build
            # value remains present in the persisted snapshot.
            defaults = formal_protocol_defaults(
                str(raw_config.get("randomization_seed") or "") or None
            )
            defaults.update(raw_config)
            default_durations = defaults["phase_durations_seconds"]
            requested_durations = raw_config.get("phase_durations_seconds") or {}
            defaults["phase_durations_seconds"] = {
                **default_durations,
                **requested_durations,
            }
            if minimum_review_seconds:
                defaults["minimum_review_seconds"] = int(minimum_review_seconds)
            # Keep the old public config field as a compatibility alias.
            if "proxy_model_version" in raw_config and "proxy_model" not in raw_config:
                defaults["proxy_model"] = raw_config["proxy_model_version"]
            try:
                config = dict(normalize_protocol_config_v2(defaults))
            except ProtocolConfigError as error:
                raise Study1ServiceError(error.code, str(error), 400) from error
        else:
            config = _normalize_experiment_config(raw_config)
        now = utc_now()
        session_id = str(uuid.uuid4())
        participant_slot_ids = [str(uuid.uuid4()) for _ in HUMAN_ROLES]
        assigned_roles = list(HUMAN_ROLES)
        if config["role_assignment_mode"] == "randomized":
            random.Random(config["randomization_seed"]).shuffle(assigned_roles)
        participants = [
            {
                "participant_id": str(uuid.uuid4()),
                "participant_slot_id": participant_slot_ids[index - 1],
                "role": role.value,
                "online": False,
                "assignment_order": index,
            }
            for index, role in enumerate(assigned_roles, start=1)
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
            "protocol_version": config.get("protocol_version", "study1-a-1.0"),
            "protocol_mode": "formal_v2" if registered_task else "legacy_protocol",
            "formal_certifiable": bool(registered_task),
            "task_definition_id": (
                registered_task["task_definition_id"] if registered_task else None
            ),
            "task_version": config["task_version"],
            "task_instance_id": config["task_instance_id"],
            "candidate_ids": (
                copy.deepcopy(registered_task["candidate_ids"])
                if registered_task
                else []
            ),
            "minimum_review_seconds": max(0, int(minimum_review_seconds)),
            "require_consent": config["require_consent"],
            "structured_instruments": config["structured_instruments"],
            "experiment_config": config,
            # ``configuration_locked_at`` is retained for legacy DTO clients;
            # formal mutability is governed by protocol_config_frozen below.
            "configuration_locked_at": utc_iso(now),
            "configuration_checksum": compute_protocol_checksum(config),
            "protocol_config_frozen": False if registered_task else True,
            "remaining_seconds": int(
                config["phase_durations_seconds"].get(Study1Phase.SETUP.value) or 0
            ),
        }
        snapshot["phase_deadline_at"] = (
            utc_iso(now + timedelta(seconds=snapshot["remaining_seconds"]))
            if snapshot["remaining_seconds"] > 0
            else None
        )
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
        material_source = (
            _registered_task_materials(registered_task)
            if registered_task
            else (materials_by_role or {})
        )
        materials = _normalize_materials(session_id, material_source, now)
        role_assignments: list[dict[str, Any]] = []
        fact_assignments: list[dict[str, Any]] = []
        initial_events: list[dict[str, Any]] = []
        if registered_task:
            participant_by_role = {
                participant["role"]: participant for participant in participants
            }
            for participant in participants:
                assignment = {
                    "assignment_id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "participant_slot_id": participant["participant_slot_id"],
                    "participant_id": participant["participant_id"],
                    "role": participant["role"],
                    "assignment_order": participant["assignment_order"],
                    "randomization_seed": config["randomization_seed"],
                    "assigned_at": now,
                }
                role_assignments.append(assignment)
                initial_events.append(
                    _assignment_event(
                        snapshot,
                        "role_assignment_created",
                        participant["participant_id"],
                        participant["role"],
                        assignment,
                        now,
                    )
                )
            for fact in registered_task["facts"]:
                for role in fact["visible_to_roles"]:
                    assignment = {
                        "assignment_id": str(uuid.uuid4()),
                        "session_id": session_id,
                        "task_definition_id": registered_task[
                            "task_definition_id"
                        ],
                        "task_version": registered_task["task_version"],
                        "fact_id": fact["fact_id"],
                        "role": role,
                        "assigned_at": now,
                    }
                    fact_assignments.append(assignment)
                    initial_events.append(
                        _assignment_event(
                            snapshot,
                            "fact_assignment_created",
                            participant_by_role[role]["participant_id"],
                            role,
                            assignment,
                            now,
                        )
                    )
        protocol_snapshot = None
        if registered_task:
            protocol_snapshot = {
                "protocol_snapshot_id": str(uuid.uuid4()),
                "session_id": session_id,
                "schema_version": "2.0",
                "protocol_mode": "formal_v2",
                "canonical_config": copy.deepcopy(config),
                "checksum": compute_protocol_checksum(
                    config,
                    registered_task,
                    role_assignments + fact_assignments,
                    materials,
                ),
                "frozen": False,
                "frozen_at": None,
                "frozen_by": None,
                "created_at": now,
            }
            snapshot["protocol_snapshot_id"] = protocol_snapshot["protocol_snapshot_id"]
            snapshot["configuration_checksum"] = protocol_snapshot["checksum"]
        self.repository.create_session(
            snapshot,
            rows,
            materials,
            role_assignments,
            fact_assignments,
            initial_events,
            protocol_snapshot,
        )
        return {
            "session": self.session_dto(snapshot),
            "invites": [invite.public_dict() for invite in created],
        }

    def clone_session(
        self,
        source_session_id: str,
        session_name: str,
        invite_ttl_seconds: int = 86400,
    ) -> dict[str, Any]:
        source = self.repository.export_data(source_session_id)
        snapshot = source.get("session")
        if not snapshot:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        materials_by_role: dict[str, list[dict[str, Any]]] = {
            role.value: [] for role in HUMAN_ROLES
        }
        for item in source.get("materials") or []:
            materials_by_role[item["role"]].append(
                {
                    "title": item.get("title"),
                    "content": item.get("content"),
                    "storage_uri": item.get("storage_uri"),
                    "metadata": item.get("metadata") or {},
                }
            )
        config = copy.deepcopy(snapshot.get("experiment_config") or {})
        config["randomization_seed"] = secrets.token_hex(8)
        return self.create_session(
            session_name,
            invite_ttl_seconds,
            materials_by_role,
            int(snapshot.get("minimum_review_seconds") or 0),
            config,
            snapshot.get("task_definition_id"),
        )

    def get_protocol_snapshot(self, session_id: str) -> dict[str, Any] | None:
        """Return the canonical protocol snapshot for a formal Session."""
        return self.repository.get_protocol_snapshot(session_id)

    def update_protocol_config(
        self,
        session_id: str,
        actor: dict[str, Any],
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        if actor.get("role") != Study1Role.RESEARCHER.value:
            raise Study1ServiceError("FORBIDDEN", "Researcher role required", 403)
        session = self.repository.get_session(session_id)
        snapshot = self.repository.get_protocol_snapshot(session_id)
        if session is None:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        if snapshot is None:
            raise Study1ServiceError(
                "LEGACY_PROTOCOL", "Legacy Sessions do not have a formal protocol", 409
            )
        if snapshot.get("frozen") or session.get("status") != "waiting":
            raise Study1ServiceError(
                "CONFIGURATION_FROZEN", "Protocol configuration is frozen", 409
            )
        if not isinstance(patch, dict):
            raise Study1ServiceError("INVALID_CONFIG", "Protocol patch must be an object", 400)
        candidate = copy.deepcopy(snapshot.get("canonical_config") or {})
        candidate.update(copy.deepcopy(patch))
        try:
            config = dict(normalize_protocol_config_v2(candidate))
        except ProtocolConfigError as error:
            raise Study1ServiceError(error.code, str(error), 400) from error
        updated = copy.deepcopy(snapshot)
        updated["canonical_config"] = config
        task = self.repository.get_task_definition(
            session.get("task_definition_id"), session.get("task_version")
        ) if session.get("task_definition_id") else None
        exported = self.repository.export_data(session_id)
        updated["checksum"] = compute_protocol_checksum(
            config,
            task,
            exported.get("role_assignments") or [],
            exported.get("materials") or [],
        )
        return self.repository.update_protocol_snapshot(session_id, updated)

    def get_materials(
        self,
        session_id: str,
        role: Study1Role | str,
        *,
        enforce_phase: bool = False,
    ) -> list[dict[str, Any]]:
        role_value = Study1Role(role)
        if role_value not in HUMAN_ROLES:
            raise Study1ServiceError(
                "MATERIAL_ACCESS_FORBIDDEN", "Role cannot access participant materials", 403
            )
        session = self.repository.get_session(session_id)
        if session is None:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        if enforce_phase:
            self._authorize(session, "material_read", role_value.value)
        return self.repository.list_materials(session_id, role_value.value)

    def add_materials(
        self, session_id: str, role: Study1Role | str, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        session = self.repository.get_session(session_id)
        if session is None:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        protocol = self.repository.get_protocol_snapshot(session_id)
        if protocol and protocol.get("frozen"):
            raise Study1ServiceError(
                "CONFIGURATION_FROZEN", "Protocol configuration is frozen", 409
            )
        self._authorize(session, "material_write", Study1Role.RESEARCHER.value)
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
        session = self.repository.get_session(session_id)
        if session is None:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        self._authorize(session, "submit", str(identity.get("role") or ""))
        if submission_type == "consent":
            payload = normalize_consent_submission(payload)
        if session.get("structured_instruments"):
            self._validate_structured_submission(
                submission_type, instrument_version, payload
            )
        if submission_type == "proxy_config":
            self._validate_proxy_config_authorization(
                session_id, identity, payload
            )
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

    def create_individual_decision(
        self,
        session_id: str,
        identity: dict[str, Any],
        kind: DecisionKind | str,
        payload: dict[str, Any],
        instrument_version: str = "2.0",
    ) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if session is None:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        if session.get("protocol_mode") != "formal_v2":
            raise Study1ServiceError("FORMAL_PROTOCOL_REQUIRED", "Formal protocol required", 409)
        self._authorize(session, "submit", str(identity.get("role") or ""))
        if not any(
            item.get("participant_id") == identity.get("participant_id")
            and item.get("role") == identity.get("role")
            for item in session.get("participants") or []
        ):
            raise Study1ServiceError("FORBIDDEN", "Participant is not assigned to this Session", 403)
        try:
            normalized = validate_individual_decision(kind, session, identity, payload)
        except DecisionValidationError as error:
            status = 403 if error.code == "FORBIDDEN" else 409 if error.code == "ACTION_NOT_ALLOWED_IN_PHASE" else 400
            raise Study1ServiceError(error.code, str(error), status) from error
        now = utc_now()
        row = {
            "decision_id": str(uuid.uuid4()),
            "session_id": session_id,
            "participant_id": identity["participant_id"],
            "role": identity["role"],
            **normalized,
            "instrument_version": str(instrument_version or "2.0"),
            "source_revision_id": None,
            "locked": True,
            "created_at": now,
        }
        created = self.repository.create_decision(row)
        completion_prefix = {
            DecisionKind.PRE_INDIVIDUAL.value: "pre_vote",
            DecisionKind.TENTATIVE_INDIVIDUAL.value: "tentative_decision",
            DecisionKind.FINAL_INDIVIDUAL.value: "final_decision",
        }[normalized["decision_kind"]]
        self.repository.mark_completion(session_id, f"{completion_prefix}:{identity['role']}")
        return created

    def get_current_instrument(
        self, session_id: str, identity: dict[str, Any]
    ) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if session is None:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        if session.get("protocol_mode") != "formal_v2":
            raise Study1ServiceError("FORMAL_PROTOCOL_REQUIRED", "Formal protocol required", 409)
        catalog = load_instrument_catalog()
        instrument = instrument_for(catalog, session["phase"], identity["role"])
        if instrument is None:
            raise Study1ServiceError(
                "INSTRUMENT_NOT_AVAILABLE", "No instrument is available in the current phase", 404
            )
        return {
            **instrument,
            "catalog_version": catalog["catalog_version"],
            "catalog_checksum": catalog["checksum"],
            "candidate_ids": copy.deepcopy(session.get("candidate_ids") or []),
        }

    def submit_instrument_response(
        self,
        session_id: str,
        identity: dict[str, Any],
        instrument_definition_id: str,
        instrument_version: str,
        ordered_responses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        instrument = self.get_current_instrument(session_id, identity)
        if (
            instrument_definition_id != instrument["instrument_definition_id"]
            or instrument_version != instrument["instrument_version"]
        ):
            raise Study1ServiceError(
                "INSTRUMENT_VERSION_MISMATCH", "Instrument identifier or version does not match", 409
            )
        try:
            normalized = validate_ordered_responses(instrument, ordered_responses)
        except InstrumentValidationError as error:
            raise Study1ServiceError(error.code, str(error), 400) from error
        content = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        response = {
            "response_id": str(uuid.uuid4()),
            "session_id": session_id,
            "participant_id": identity["participant_id"],
            "role": identity["role"],
            "instrument_definition_id": instrument_definition_id,
            "instrument_version": instrument_version,
            "phase": instrument["phase"],
            "ordered_responses": normalized,
            "response_checksum": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "submitted_at": utc_now(),
        }
        created = self.repository.create_instrument_response(response)
        completion_by_phase = {
            Study1Phase.DELEGATION_EXPECTATION.value: "delegation_expectation",
            Study1Phase.COMPREHENSION_MEASUREMENT.value: "comprehension_measurement",
            Study1Phase.POST_SURVEY.value: "post_survey",
        }
        completion_prefix = completion_by_phase.get(instrument["phase"])
        if completion_prefix:
            self.repository.mark_completion(
                session_id, f"{completion_prefix}:{identity['role']}"
            )
        return created

    def get_shared_artifact(
        self,
        session_id: str,
        identity: dict[str, Any],
        kind: SharedArtifactKind | str,
    ) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if session is None:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        if session.get("protocol_mode") != "formal_v2":
            raise Study1ServiceError("FORMAL_PROTOCOL_REQUIRED", "Formal protocol required", 409)
        try:
            artifact_kind = validate_shared_artifact_context(kind, session, identity)
        except SharedArtifactValidationError as error:
            status = 403 if error.code == "FORBIDDEN" else 409
            raise Study1ServiceError(error.code, str(error), status) from error
        self._authorize(session, "submit", str(identity.get("role") or ""))
        artifact = self.repository.get_shared_artifact(session_id, artifact_kind.value)
        if artifact is not None:
            return artifact
        return {
            "shared_artifact_id": None,
            "session_id": session_id,
            "kind": artifact_kind.value,
            "current_revision_id": None,
            "locked_revision_id": None,
            "locked_at": None,
            "current_revision": None,
            "locked": False,
        }

    def create_shared_revision(
        self,
        session_id: str,
        identity: dict[str, Any],
        kind: SharedArtifactKind | str,
        parent_revision_id: str | None,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if session is None:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        if session.get("protocol_mode") != "formal_v2":
            raise Study1ServiceError("FORMAL_PROTOCOL_REQUIRED", "Formal protocol required", 409)
        try:
            artifact_kind = validate_shared_artifact_context(kind, session, identity)
            normalized = validate_shared_content(artifact_kind, session, content)
        except SharedArtifactValidationError as error:
            status = 403 if error.code == "FORBIDDEN" else 409 if error.code == "ACTION_NOT_ALLOWED_IN_PHASE" else 400
            raise Study1ServiceError(error.code, str(error), status) from error
        self._authorize(session, "submit", str(identity.get("role") or ""))
        return self.repository.create_shared_revision(
            session_id,
            artifact_kind.value,
            parent_revision_id,
            normalized,
            identity,
        )

    def confirm_shared_revision(
        self,
        session_id: str,
        identity: dict[str, Any],
        kind: SharedArtifactKind | str,
        revision_id: str,
    ) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if session is None:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        if session.get("protocol_mode") != "formal_v2":
            raise Study1ServiceError("FORMAL_PROTOCOL_REQUIRED", "Formal protocol required", 409)
        try:
            artifact_kind = validate_shared_artifact_context(kind, session, identity)
        except SharedArtifactValidationError as error:
            status = 403 if error.code == "FORBIDDEN" else 409
            raise Study1ServiceError(error.code, str(error), status) from error
        self._authorize(session, "submit", str(identity.get("role") or ""))
        if not str(revision_id or "").strip():
            raise Study1ServiceError(
                "SHARED_REVISION_REQUIRED", "revision_id is required", 400
            )
        return self.repository.confirm_shared_revision(
            session_id, artifact_kind.value, revision_id, identity
        )

    def _validate_structured_submission(
        self,
        submission_type: str,
        instrument_version: str,
        payload: dict[str, Any],
    ) -> None:
        required = STRUCTURED_SUBMISSION_FIELDS.get(submission_type)
        if required is None:
            return
        if not str(instrument_version or "").startswith("2."):
            raise Study1ServiceError(
                "INSTRUMENT_VERSION_REQUIRED",
                f"{submission_type} must use the locked Study 1 instrument version 2.x",
                400,
            )
        if not isinstance(payload, dict):
            raise Study1ServiceError("INVALID_PAYLOAD", "payload must be an object", 400)
        missing = [
            field
            for field in required
            if field not in payload
            or payload[field] is None
            or (isinstance(payload[field], str) and not payload[field].strip())
        ]
        if missing:
            raise Study1ServiceError(
                "INCOMPLETE_INSTRUMENT",
                "Required fields are missing: " + ", ".join(missing),
                400,
            )
        for field in (
            "confidence",
            "expected_principal_acceptance",
            "understanding",
            "proxy_trust",
            "team_synchronization",
        ):
            if field in payload:
                try:
                    value = int(payload[field])
                except (TypeError, ValueError) as error:
                    raise Study1ServiceError(
                        "INVALID_SCALE_VALUE", f"{field} must be an integer from 1 to 7", 400
                    ) from error
                if value < 1 or value > 7:
                    raise Study1ServiceError(
                        "INVALID_SCALE_VALUE", f"{field} must be between 1 and 7", 400
                    )
        if submission_type == "consent":
            if not all(
                payload.get(field) is True
                for field in (
                    "identity_confirmed",
                    "role_confirmed",
                    "voluntary_participation_confirmed",
                )
            ):
                raise Study1ServiceError(
                    "CONSENT_REQUIRED",
                    "Identity, role, and voluntary participation confirmations are required",
                    400,
                )
            missing_scopes = missing_required_consent_scopes(payload)
            if missing_scopes:
                raise Study1ServiceError(
                    "CONSENT_SCOPE_REQUIRED",
                    "Required consent scopes are missing: " + ", ".join(missing_scopes),
                    400,
                )

    def _validate_proxy_config_authorization(
        self,
        session_id: str,
        identity: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        if identity.get("role") != Study1Role.PRINCIPAL.value:
            return
        if not isinstance(payload, dict) or payload.get("authorization_confirmed") is not True:
            raise Study1ServiceError(
                "PROXY_AUTHORIZATION_REQUIRED",
                "P must explicitly confirm the Proxy material authorization",
                400,
            )
        if (
            "authority_level" in payload
            and payload.get("authority_level") not in PROXY_AUTHORITY_LEVELS
        ):
            raise Study1ServiceError(
                "INVALID_PROXY_AUTHORITY_LEVEL",
                "authority_level must be share_only, suggest, or agree_tentative",
                400,
            )
        material_ids = payload.get("authorized_material_ids")
        if not isinstance(material_ids, list) or any(
            not isinstance(item, str) or not item for item in material_ids
        ):
            raise Study1ServiceError(
                "INVALID_PROXY_MATERIAL_AUTHORIZATION",
                "authorized_material_ids must be a list of material IDs",
                400,
            )
        if len(set(material_ids)) != len(material_ids):
            raise Study1ServiceError(
                "INVALID_PROXY_MATERIAL_AUTHORIZATION",
                "authorized_material_ids must not contain duplicates",
                400,
            )
        principal_material_ids = {
            item["material_id"]
            for item in self.repository.list_materials(
                session_id, Study1Role.PRINCIPAL.value
            )
        }
        if not set(material_ids) <= principal_material_ids:
            raise Study1ServiceError(
                "INVALID_PROXY_MATERIAL_AUTHORIZATION",
                "P can authorize only P's own Hidden Profile materials",
                400,
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
        session = self.repository.get_session(session_id)
        if session is None:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        self._authorize(session, "advance", str(actor.get("role") or ""))
        completion_override = None
        if session.get("protocol_mode") == "formal_v2":
            completion_override = self._project_snapshot(session).get("completion") or {}
        try:
            snapshot, events = self.repository.transition(
                session_id,
                target_phase,
                actor,
                reason,
                override,
                completion_override=completion_override,
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
        if action == "start":
            current = self.repository.get_session(session_id)
            if current is None:
                raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
            current_projected = self._project_snapshot(current)
            missing = self._readiness_for_snapshot(current_projected)[
                "missing_prerequisites"
            ]
            if missing:
                raise Study1ServiceError(
                    "PREREQUISITES_NOT_MET",
                    "Missing prerequisites: " + ", ".join(missing),
                    409,
                )
            protocol = self.repository.get_protocol_snapshot(session_id)
            if protocol and not protocol.get("frozen"):
                exported = self.repository.export_data(session_id)
                task = self.repository.get_task_definition(
                    current.get("task_definition_id"), current.get("task_version")
                ) if current.get("task_definition_id") else None
                frozen = freeze_protocol_snapshot(
                    protocol,
                    task=task,
                    assignments=(exported.get("role_assignments") or [])
                    + (exported.get("fact_assignments") or []),
                    materials=exported.get("materials") or [],
                    actor=actor,
                )
                self.repository.update_protocol_snapshot(session_id, frozen)
        snapshot, events = self.repository.control_session(
            session_id, action, actor, payload or {}
        )
        if action == "terminate":
            self.issue_media_command(
                session_id,
                actor,
                "STOP_SESSION",
                {"reason": str((payload or {}).get("reason") or "session_terminated")},
                command_id=str(
                    uuid.uuid5(uuid.NAMESPACE_URL, f"study1:{session_id}:stop-session")
                ),
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
        data = self.repository.export_data(session_id)
        session = self._project_snapshot(data["session"], data)
        return _dashboard_payload(
            session,
            data.get("artifacts") or [],
            data.get("incidents") or [],
        )

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
        if command != "STOP_SESSION":
            self._authorize(session, "issue_media_command", str(actor.get("role") or ""))
        required = {
            "START_PROXY_MEETING": Study1Phase.PROXY_MEETING.value,
            "BEGIN_HANDOFF": Study1Phase.HANDOFF.value,
            "START_SYNC_MEETING": Study1Phase.SYNC_MEETING.value,
            "REGENERATE_SUMMARY": Study1Phase.REVIEW.value,
        }.get(command)
        if required and session["phase"] != required:
            raise ActionNotAllowedInPhase(session["phase"], required)
        command_payload = copy.deepcopy(payload or {})
        if command == "START_PROXY_MEETING":
            command_payload = {
                "authorized_context": self._proxy_authorized_context(session_id)
            }
        if command == "END_CURRENT_MEETING" and session["phase"] not in (
            Study1Phase.PROXY_MEETING.value,
            Study1Phase.SYNC_MEETING.value,
        ):
            raise Study1ServiceError(
                "MEDIA_COMMAND_NOT_ALLOWED",
                "END_CURRENT_MEETING requires an active meeting phase",
                409,
            )
        release_identity = study1_release_identity_from_env()
        if release_identity:
            command_payload["release"] = release_identity
        envelope = {
            "command_id": command_id or str(uuid.uuid4()),
            "session_id": session_id,
            "phase_version": session["phase_version"],
            "command": command,
            "issued_at": utc_iso(),
            "payload": command_payload,
        }
        created = self.repository.record_media_command(session_id, envelope)
        try:
            result = self.media_gateway.send_command(envelope)
        except MediaGatewayError as error:
            raise Study1ServiceError(
                "MEDIA_SERVICE_UNAVAILABLE", str(error), 502
            ) from error
        return {"command": envelope, "duplicate": not created, "gateway": result}

    def handle_summary_failure_action(
        self, session_id: str, actor: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        if actor.get("role") != Study1Role.RESEARCHER.value:
            raise Study1ServiceError("FORBIDDEN", "Researcher role required", 403)
        try:
            action = build_summary_failure_action(
                action=str(payload.get("action") or ""),
                reason=str(payload.get("reason") or ""),
                frozen_config_checksum=payload.get("frozen_config_checksum"),
                approved_config_checksum=payload.get("approved_config_checksum"),
                source_transcript_checksum=payload.get("source_transcript_checksum"),
                source_summary_version=payload.get("source_summary_version"),
            )
        except SummaryPolicyError as error:
            raise Study1ServiceError(error.code, str(error), 400) from error
        if action.get("media_command"):
            issued = self.issue_media_command(
                session_id,
                actor,
                str(action["media_command"]),
                action["payload"],
            )
            return {"action": action, "media": issued}
        return {"action": action}

    def record_summary_qa(
        self,
        session_id: str,
        actor: dict[str, Any],
        summary_artifact_id: str,
        ratings: dict[str, Any],
    ) -> dict[str, Any]:
        if actor.get("role") != Study1Role.RESEARCHER.value:
            raise Study1ServiceError("FORBIDDEN", "Researcher role required", 403)
        data = self.repository.export_data(session_id)
        summaries = [
            item
            for item in data.get("artifacts") or []
            if item.get("type") == "summary"
            and item.get("artifact_id") == summary_artifact_id
        ]
        if not summaries:
            raise Study1ServiceError(
                "SUMMARY_ARTIFACT_NOT_FOUND", "Summary artifact was not found", 404
            )
        try:
            entry = SummaryQaService().record(
                session_id=session_id,
                summary_artifact_id=summary_artifact_id,
                researcher_id=str(actor.get("participant_id") or "researcher"),
                ratings=ratings or {},
            )
        except SummaryPolicyError as error:
            raise Study1ServiceError(error.code, str(error), 400) from error
        existing = [
            item
            for item in data.get("artifacts") or []
            if item.get("type") == "summary_qa"
        ]
        artifact_result = self.create_artifact(
            session_id,
            {
                "type": "summary_qa",
                "version": str(len(existing) + 1),
                "content": json.dumps(entry.public_dict(), ensure_ascii=False),
                "generator_version": "human-researcher-summary-qa-v1",
                "metadata": {
                    "source_summary_artifact_id": summary_artifact_id,
                    "private_researcher_qa": True,
                },
            },
        )
        return {"qa": entry.public_dict(), "artifact": artifact_result["artifact"]}

    def _proxy_authorized_context(self, session_id: str) -> dict[str, Any]:
        data = self.repository.export_data(session_id)
        configs = [
            item
            for item in data.get("submissions") or []
            if item.get("submission_type") == "proxy_config"
            and item.get("role") == Study1Role.PRINCIPAL.value
            and item.get("locked", True)
        ]
        config = configs[-1] if configs else None
        if not config:
            raise Study1ServiceError(
                "PROXY_CONFIGURATION_REQUIRED",
                "P must submit and lock Proxy configuration before the meeting",
                409,
            )
        config_payload = copy.deepcopy(config.get("payload") or {})
        if config_payload.get("authorization_confirmed") is not True:
            raise Study1ServiceError(
                "PROXY_AUTHORIZATION_REQUIRED",
                "P must explicitly authorize Proxy materials before the meeting",
                409,
            )
        authorized_ids = config_payload.get("authorized_material_ids")
        if not isinstance(authorized_ids, list):
            raise Study1ServiceError(
                "INVALID_PROXY_MATERIAL_AUTHORIZATION",
                "Proxy material authorization is invalid",
                409,
            )
        authorized_id_set = set(authorized_ids)
        materials = [
            {
                key: item.get(key)
                for key in ("material_id", "title", "content", "storage_uri", "checksum")
            }
            for item in data.get("materials") or []
            if item.get("role") == Study1Role.PRINCIPAL.value
            and item.get("material_id") in authorized_id_set
        ]
        if {item["material_id"] for item in materials} != authorized_id_set:
            raise Study1ServiceError(
                "INVALID_PROXY_MATERIAL_AUTHORIZATION",
                "Authorized Proxy material no longer belongs to P",
                409,
            )
        config_id = config["submission_id"]
        return {
            "authorization_submission_id": config_id,
            "proxy_config_submission_id": config_id,
            "materials": materials,
            "proxy_config": config_payload,
        }

    def issue_media_access(
        self, session_id: str, identity: dict[str, Any]
    ) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        role = str(identity.get("role") or "")
        self._authorize(session, "issue_media_access", role)
        allowed = {
            Study1Phase.PROXY_MEETING.value: {
                Study1Role.TEAMMATE_1.value,
                Study1Role.TEAMMATE_2.value,
            },
            Study1Phase.SYNC_MEETING.value: {
                Study1Role.PRINCIPAL.value,
                Study1Role.TEAMMATE_1.value,
                Study1Role.TEAMMATE_2.value,
            },
            Study1Phase.HANDOFF.value: {
                Study1Role.PRINCIPAL.value,
                Study1Role.TEAMMATE_1.value,
                Study1Role.TEAMMATE_2.value,
            },
        }
        if role not in allowed.get(session["phase"], set()):
            raise Study1ServiceError(
                "MEDIA_ACCESS_FORBIDDEN",
                "Role is not allowed in the current media room",
                403,
            )
        request_payload = {
            "session_id": session_id,
            "phase": session["phase"],
            "phase_version": session["phase_version"],
            "role": role,
            "participant_id": identity["participant_id"],
        }
        try:
            return self.media_gateway.issue_access(request_payload)
        except MediaGatewayError as error:
            raise Study1ServiceError(
                "MEDIA_SERVICE_UNAVAILABLE", str(error), 502
            ) from error

    def media_status(self, session_id: str) -> dict[str, Any]:
        if not self.repository.get_session(session_id):
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        try:
            return self.media_gateway.get_status(session_id)
        except MediaGatewayError as error:
            raise Study1ServiceError(
                "MEDIA_SERVICE_UNAVAILABLE", str(error), 502
            ) from error

    def get_recording(
        self,
        session_id: str,
        identity: dict[str, Any],
        recording_id: str,
        range_header: str | None,
    ):
        session = self.repository.get_session(session_id)
        if not session:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        allowed_phases = (
            Study1Phase.REVIEW.value,
            Study1Phase.COMPREHENSION_MEASUREMENT.value,
        )
        is_researcher = identity.get("role") == Study1Role.RESEARCHER.value
        is_principal_review = (
            identity.get("role") == Study1Role.PRINCIPAL.value
            and session["phase"] in allowed_phases
            and session.get("completion", {}).get("delegation_expectation:principal")
        )
        if not (is_researcher or is_principal_review):
            raise Study1ServiceError(
                "MEDIA_REPLAY_FORBIDDEN",
                "Recording replay is available only to P during Review",
                403,
            )
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.wav", recording_id):
            raise Study1ServiceError(
                "RECORDING_NOT_FOUND", "Recording not found", 404
            )
        if not range_header or not re.fullmatch(r"bytes=\d+-\d*", range_header):
            raise Study1ServiceError(
                "RECORDING_RANGE_REQUIRED",
                "A bounded byte Range is required",
                416,
            )
        start_text, end_text = range_header[6:].split("-", 1)
        start = int(start_text)
        end = int(end_text) if end_text else start + 1_048_575
        if end < start or end - start + 1 > 1_048_576:
            raise Study1ServiceError(
                "RECORDING_RANGE_TOO_LARGE",
                "Recording Range cannot exceed 1 MiB",
                416,
            )
        bounded_range = f"bytes={start}-{end}"
        try:
            return self.media_gateway.get_recording(
                session_id, recording_id, bounded_range
            )
        except MediaGatewayError as error:
            raise Study1ServiceError(
                "MEDIA_SERVICE_UNAVAILABLE", str(error), 502
            ) from error

    def report_media_device(
        self,
        session_id: str,
        identity: dict[str, Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        state = str(data.get("state") or "")
        if state not in {"ready", "denied", "missing", "error"}:
            raise Study1ServiceError(
                "INVALID_DEVICE_STATE", "Invalid microphone device state", 400
            )
        device = data.get("device") or {}
        if not isinstance(device, dict):
            raise Study1ServiceError(
                "INVALID_DEVICE", "device must be an object", 400
            )
        payload = {
            "session_id": session_id,
            "phase_version": session["phase_version"],
            "participant_id": identity["participant_id"],
            "role": identity["role"],
            "state": state,
            "device": {
                key: str(device.get(key) or "")[:256]
                for key in ("kind", "label")
                if device.get(key)
            },
        }
        try:
            return self.media_gateway.report_device(payload)
        except MediaGatewayError as error:
            raise Study1ServiceError(
                "MEDIA_SERVICE_UNAVAILABLE", str(error), 502
            ) from error

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

    def create_transcript_correction(
        self,
        session_id: str,
        actor: dict[str, Any],
        segment_id: str,
        corrected_text: str,
        reason: str,
    ) -> dict[str, Any]:
        if actor.get("role") != Study1Role.RESEARCHER.value:
            raise Study1ServiceError("FORBIDDEN", "Researcher role required", 403)
        clean_segment_id = segment_id.strip()
        clean_text = corrected_text.strip()
        clean_reason = reason.strip()
        if not clean_segment_id or not clean_text or not clean_reason:
            raise Study1ServiceError(
                "TRANSCRIPT_CORRECTION_FIELDS_REQUIRED",
                "segment_id, corrected_text, and reason are required",
                400,
            )
        data = self.repository.export_data(session_id)
        transcripts = [
            item for item in data.get("artifacts") or [] if item.get("type") == "transcript"
        ]
        if not transcripts:
            raise Study1ServiceError(
                "TRANSCRIPT_NOT_FOUND", "No source transcript is available", 404
            )
        source = transcripts[-1]
        try:
            segments = json.loads(source.get("content") or "[]")
        except json.JSONDecodeError as error:
            raise Study1ServiceError(
                "TRANSCRIPT_NOT_STRUCTURED", "Source transcript is not structured JSON", 409
            ) from error
        original = next(
            (
                item for item in segments
                if str(item.get("segment_id") or "") == clean_segment_id
            ),
            None,
        )
        if original is None:
            raise Study1ServiceError(
                "TRANSCRIPT_SEGMENT_NOT_FOUND", "Transcript segment was not found", 404
            )
        existing = [
            item for item in data.get("artifacts") or []
            if item.get("type") == "transcript_correction"
        ]
        content = json.dumps(
            {
                "segment_id": clean_segment_id,
                "original_text": str(original.get("text") or ""),
                "corrected_text": clean_text,
                "reason": clean_reason,
                "corrected_by": actor.get("participant_id"),
                "corrected_at": utc_iso(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return self.create_artifact(
            session_id,
            {
                "type": "transcript_correction",
                "version": str(len(existing) + 1),
                "content": content,
                "generator_version": "human-researcher-correction-v1",
                "metadata": {
                    "source_transcript_artifact_id": source.get("artifact_id"),
                    "source_transcript_checksum": source.get("checksum"),
                    "append_only": True,
                },
            },
        )

    def export_bundle(self, session_id: str):
        from .export_service import build_study1_export, merge_media_export

        data = self.repository.export_data(session_id)
        session = data["session"]
        if session.get("task_definition_id"):
            data["task_definition"] = self.repository.get_task_definition(
                session["task_definition_id"], session.get("task_version")
            )
        workflow = build_study1_export(data)
        try:
            media = self.media_gateway.export_bundle(session_id)
            return merge_media_export(workflow, media)
        except MediaGatewayError as error:
            return merge_media_export(workflow, None, str(error))

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

    def record_quality_metrics(
        self,
        session_id: str,
        identity: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        session = self.repository.get_session(session_id)
        if not session:
            raise Study1ServiceError("SESSION_NOT_FOUND", "Session not found", 404)
        metric = normalize_rtc_metric(
            session_id, identity, payload or {}, received_at=utc_now()
        )
        event = self.repository.record_ui_event(
            session_id, identity, "rtc_metric_sample", metric
        )
        try:
            self.media_gateway.report_rtc_metrics(
                {
                    "session_id": session_id,
                    "phase_version": session["phase_version"],
                    "participant_id": identity["participant_id"],
                    "role": identity["role"],
                    "samples": [metric],
                }
            )
        except MediaGatewayError:
            pass
        return event

    def quality_snapshot(
        self, session_id: str, actor: dict[str, Any]
    ) -> dict[str, Any]:
        if actor.get("role") != Study1Role.RESEARCHER.value:
            raise Study1ServiceError("FORBIDDEN", "Researcher role required", 403)
        data = self.repository.export_data(session_id)
        try:
            media_status = self.media_gateway.get_status(session_id)
        except MediaGatewayError as error:
            media_status = {
                "service_status": "unavailable",
                "last_error": str(error),
                "components": {},
            }
        return build_quality_snapshot(
            session_id=session_id,
            data=data,
            media_status=media_status,
            now=utc_now(),
        )

    def record_review_event_batch(
        self,
        session_id: str,
        identity: dict[str, Any],
        visit_id: str,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self.repository.record_review_event_batch(
            session_id, identity, visit_id, events
        )

    def create_marker(
        self,
        session_id: str,
        actor: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.repository.create_marker(session_id, actor, payload or {})
        except MarkerValidationError as error:
            status = 403 if error.code == "FORBIDDEN" else 400
            raise Study1ServiceError(error.code, str(error), status) from error

    def list_markers(
        self, session_id: str, actor: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return self.repository.list_markers(session_id, actor)

    def generate_replay_plan(
        self,
        session_id: str,
        actor: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if actor.get("role") != Study1Role.RESEARCHER.value:
            raise Study1ServiceError("FORBIDDEN", "Researcher role required", 403)
        try:
            return self.repository.create_replay_plan(session_id, actor, payload or {})
        except ReplayValidationError as error:
            raise Study1ServiceError(error.code, str(error), 400) from error

    def list_replay_plans(
        self, session_id: str, actor: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return self.repository.list_replay_plans(session_id, actor)

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
        projected = self._project_snapshot(snapshot)
        state = self._readiness_for_snapshot(projected)
        base = {
            "session_id": projected["session_id"],
            "status": projected["status"],
            "phase": projected["phase"],
            "phase_version": projected["phase_version"],
            "phase_started_at": projected["phase_started_at"],
            "remaining_seconds": _remaining_seconds(projected),
            "protocol_mode": projected.get("protocol_mode", "legacy_protocol"),
            "formal_certifiable": bool(projected.get("formal_certifiable", False)),
            "task_definition_id": projected.get("task_definition_id"),
            "task_version": projected.get("task_version"),
            **state,
            "consent_version": (projected.get("experiment_config") or {}).get(
                "consent_version", "study1-consent-v1"
            ),
            "structured_instruments": bool(projected.get("structured_instruments")),
        }
        if role in {item.value for item in HUMAN_ROLES}:
            completion = projected.get("completion") or {}
            base["my_completed_actions"] = sorted(
                key for key, completed in completion.items()
                if completed is True and key.endswith(f":{role}")
            )
        if role:
            base["capabilities"] = formal_capabilities(projected, role)
        if role == Study1Role.PRINCIPAL.value and projected["phase"] == "PROXY_MEETING":
            return {
                **base,
                "waiting_room": {
                    "message": "The delegated discussion is in progress.",
                    "remaining_seconds": projected.get("remaining_seconds"),
                    "connection_status": "connected",
                },
            }
        return base

    def _project_snapshot(
        self,
        snapshot: dict[str, Any],
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if snapshot.get("protocol_mode") != "formal_v2":
            return snapshot
        exported = data
        if exported is None:
            exported = self.repository.export_data(snapshot["session_id"])
        return project_formal_session(snapshot, exported)

    def _readiness_for_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        if snapshot.get("protocol_mode") == "formal_v2":
            return formal_readiness(snapshot)
        return readiness(snapshot)


def _registered_task_materials(
    task: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    materials: dict[str, list[dict[str, Any]]] = {}
    for role in (item.value for item in HUMAN_ROLES):
        visible_facts = [
            copy.deepcopy(fact)
            for fact in task["facts"]
            if role in fact["visible_to_roles"]
        ]
        materials[role] = [
            {
                "title": task["title"],
                "content": "\n".join(fact["text"] for fact in visible_facts),
                "metadata": {
                    "task_definition_id": task["task_definition_id"],
                    "task_version": task["task_version"],
                    "candidate_ids": copy.deepcopy(task["candidate_ids"]),
                    "facts": visible_facts,
                },
            }
        ]
    return materials


def _assignment_event(
    session: dict[str, Any],
    event_type: str,
    participant_id: str,
    role: str,
    assignment: dict[str, Any],
    occurred_at: datetime,
) -> dict[str, Any]:
    payload = {
        key: copy.deepcopy(value)
        for key, value in assignment.items()
        if key not in {"session_id", "assigned_at"}
    }
    return {
        "event_id": str(uuid.uuid4()),
        "session_id": session["session_id"],
        "participant_id": participant_id,
        "role": role,
        "phase": session["phase"],
        "phase_version": session["phase_version"],
        "event_type": event_type,
        "occurred_at": utc_iso(occurred_at),
        "payload": payload,
    }


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
            metadata = copy.deepcopy(item.get("metadata") or {})
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
                    "metadata_payload": metadata,
                }
            )
    visibility_by_text: dict[str, set[str]] = {}
    for row in rows:
        for text in _material_fact_texts(row.get("content")):
            visibility_by_text.setdefault(text.casefold(), set()).add(row["role"])
    for row in rows:
        if row["metadata_payload"].get("facts"):
            _validate_material_facts(row["metadata_payload"]["facts"], row["role"])
            continue
        facts = []
        for index, text in enumerate(_material_fact_texts(row.get("content")), start=1):
            visible_to = sorted(visibility_by_text[text.casefold()])
            facts.append(
                {
                    "fact_id": f"{row['role']}-f{index}-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:10]}",
                    "text": text,
                    "candidate_id": "unspecified",
                    "valence": "neutral",
                    "information_type": "shared" if len(visible_to) > 1 else "unique",
                    "visible_to_roles": visible_to,
                }
            )
        row["metadata_payload"]["facts"] = facts
    return rows


def _material_fact_texts(content: Any) -> list[str]:
    if content is None:
        return []
    return [
        value.strip()
        for value in re.split(r"(?:\r?\n)+|(?<=[。！？.!?])\s+", str(content))
        if value.strip()
    ]


def _validate_material_facts(facts: Any, material_role: str) -> None:
    if not isinstance(facts, list) or not facts:
        raise Study1ServiceError("INVALID_MATERIAL_FACTS", "facts must be a non-empty list", 400)
    seen: set[str] = set()
    for fact in facts:
        if not isinstance(fact, dict):
            raise Study1ServiceError("INVALID_MATERIAL_FACTS", "each fact must be an object", 400)
        required = (
            "fact_id",
            "text",
            "candidate_id",
            "valence",
            "information_type",
            "visible_to_roles",
        )
        if any(fact.get(field) in (None, "", []) for field in required):
            raise Study1ServiceError(
                "INVALID_MATERIAL_FACTS",
                "each fact requires fact_id, text, candidate_id, valence, information_type, and visible_to_roles",
                400,
            )
        if fact["fact_id"] in seen:
            raise Study1ServiceError("INVALID_MATERIAL_FACTS", "fact_id values must be unique", 400)
        seen.add(fact["fact_id"])
        if material_role not in fact["visible_to_roles"]:
            raise Study1ServiceError(
                "INVALID_MATERIAL_FACTS",
                "a material fact must be visible to its assigned role",
                400,
            )


def _normalize_experiment_config(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Study1ServiceError(
            "INVALID_EXPERIMENT_CONFIG", "experiment_config must be an object", 400
        )
    durations = value.get("phase_durations_seconds") or {}
    if not isinstance(durations, dict):
        raise Study1ServiceError(
            "INVALID_PHASE_DURATIONS", "phase_durations_seconds must be an object", 400
        )
    clean_durations: dict[str, int] = {}
    valid_phases = {phase.value for phase in Study1Phase}
    for phase, seconds in durations.items():
        if phase not in valid_phases:
            raise Study1ServiceError("INVALID_PHASE_DURATIONS", f"Unknown phase: {phase}", 400)
        try:
            clean_seconds = int(seconds)
        except (TypeError, ValueError) as error:
            raise Study1ServiceError(
                "INVALID_PHASE_DURATIONS", f"Duration for {phase} must be an integer", 400
            ) from error
        if clean_seconds < 0 or clean_seconds > 86400:
            raise Study1ServiceError(
                "INVALID_PHASE_DURATIONS", f"Duration for {phase} must be 0-86400", 400
            )
        clean_durations[phase] = clean_seconds
    return {
        "task_version": str(value.get("task_version") or "2.0")[:64],
        "task_instance_id": str(value.get("task_instance_id") or "study1-default")[:128],
        "summary_template_version": str(
            value.get("summary_template_version") or "study1-five-section-v1"
        )[:64],
        "transcript_access_policy": str(
            value.get("transcript_access_policy") or "principal_after_delegation"
        )[:64],
        "proxy_model_version": str(value.get("proxy_model_version") or "configured-at-runtime")[:128],
        "consent_version": str(value.get("consent_version") or "study1-consent-v1")[:64],
        "role_assignment_mode": str(value.get("role_assignment_mode") or "fixed")[:32],
        "randomization_seed": str(value.get("randomization_seed") or secrets.token_hex(8))[:64],
        "phase_durations_seconds": clean_durations,
        "require_consent": bool(value.get("require_consent", False)),
        "structured_instruments": bool(value.get("structured_instruments", False)),
    }


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
    allowed = {
        "transcript",
        "summary",
        "recording_manifest",
        "agent_log_manifest",
        "transcript_correction",
        "summary_qa",
    }
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
