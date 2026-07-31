"""Domain constants shared by the Study 1 service.

Database rows are added in the authentication/data commits.  Keeping the role
and phase vocabulary here gives the state machine, permissions, routes, export,
and frontend contract one canonical spelling.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from services.db import Base


class Study1Role(StrEnum):
    PRINCIPAL = "principal"
    TEAMMATE_1 = "teammate_1"
    TEAMMATE_2 = "teammate_2"
    RESEARCHER = "researcher"
    PROXY = "proxy"


HUMAN_ROLES = (
    Study1Role.PRINCIPAL,
    Study1Role.TEAMMATE_1,
    Study1Role.TEAMMATE_2,
)


class Study1Phase(StrEnum):
    SETUP = "SETUP"
    MATERIAL_READING = "MATERIAL_READING"
    PRE_VOTE = "PRE_VOTE"
    PROXY_CONFIGURATION = "PROXY_CONFIGURATION"
    PROXY_MEETING = "PROXY_MEETING"
    TENTATIVE_DECISION = "TENTATIVE_DECISION"
    DELEGATION_EXPECTATION = "DELEGATION_EXPECTATION"
    REVIEW = "REVIEW"
    COMPREHENSION_MEASUREMENT = "COMPREHENSION_MEASUREMENT"
    HANDOFF = "HANDOFF"
    SYNC_MEETING = "SYNC_MEETING"
    FINAL_DECISION = "FINAL_DECISION"
    FOLLOWUP_TASK = "FOLLOWUP_TASK"
    POST_SURVEY = "POST_SURVEY"
    COMPLETED = "COMPLETED"


PHASE_ORDER = tuple(Study1Phase)
PHASE_SCHEMA_VERSION = "1.0"

JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class Study1InviteRow(Base):
    __tablename__ = "study1_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invite_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    participant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("session_id", "role", name="uq_study1_invites_session_role"),
        Index("ix_study1_invites_session_participant", "session_id", "participant_id"),
    )


class Study1EventRow(Base):
    __tablename__ = "study1_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    participant_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    phase_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)

    __table_args__ = (
        Index("ix_study1_events_session_time", "session_id", "occurred_at"),
    )


class Study1SubmissionRow(Base):
    __tablename__ = "study1_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    participant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    server_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    client_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    locked: Mapped[bool] = mapped_column(nullable=False, default=True)
    previous_submission_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    revision_operator: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    revision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_study1_submissions_session_participant", "session_id", "participant_id"),
    )


class Study1ArtifactRow(Base):
    __tablename__ = "study1_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storage_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_VALUE, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "session_id", "type", "version", name="uq_study1_artifact_version"
        ),
    )


class Study1IncidentRow(Base):
    __tablename__ = "study1_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_VALUE, nullable=False
    )


class Study1MaterialRow(Base):
    __tablename__ = "study1_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storage_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_VALUE, nullable=False
    )

    __table_args__ = (
        Index("ix_study1_materials_session_role", "session_id", "role"),
    )


class Study1SchemaVersionRow(Base):
    __tablename__ = "study1_schema_versions"

    revision: Mapped[str] = mapped_column(String(128), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Study1TaskDefinitionRow(Base):
    __tablename__ = "study1_task_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_definition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    task_version: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    candidate_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "task_definition_id",
            "task_version",
            name="uq_study1_task_definition_version",
        ),
    )


class Study1TaskFactRow(Base):
    __tablename__ = "study1_task_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_definition_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    task_version: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    valence: Mapped[str] = mapped_column(String(32), nullable=False)
    information_type: Mapped[str] = mapped_column(String(32), nullable=False)
    visible_to_roles: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "task_definition_id",
            "task_version",
            "fact_id",
            name="uq_study1_task_fact_id",
        ),
        Index(
            "ix_study1_task_facts_candidate",
            "task_definition_id",
            "task_version",
            "candidate_id",
        ),
    )


class Study1RoleAssignmentRow(Base):
    __tablename__ = "study1_role_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    participant_slot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    participant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    assignment_order: Mapped[int] = mapped_column(Integer, nullable=False)
    randomization_seed: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "role", name="uq_study1_role_assignment_role"),
        UniqueConstraint(
            "session_id", "participant_slot_id", name="uq_study1_role_assignment_slot"
        ),
        UniqueConstraint(
            "session_id", "participant_id", name="uq_study1_role_assignment_participant"
        ),
    )


class Study1FactAssignmentRow(Base):
    __tablename__ = "study1_fact_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    task_definition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    task_version: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "session_id", "fact_id", "role", name="uq_study1_fact_assignment"
        ),
        Index(
            "ix_study1_fact_assignments_task",
            "task_definition_id",
            "task_version",
            "fact_id",
        ),
    )


class Study1ProtocolSnapshotRow(Base):
    __tablename__ = "study1_protocol_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    protocol_snapshot_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    protocol_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_config: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    frozen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    frozen_by: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Study1DecisionRow(Base):
    __tablename__ = "study1_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    decision_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    participant_id: Mapped[Optional[str]] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[int]] = mapped_column(Integer)
    ratings: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    decision_status: Mapped[Optional[str]] = mapped_column(String(32))
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_revision_id: Mapped[Optional[str]] = mapped_column(String(36))
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "decision_kind",
            "participant_id",
            name="uq_study1_individual_decision",
        ),
    )


class Study1SharedArtifactRow(Base):
    __tablename__ = "study1_shared_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shared_artifact_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    current_revision_id: Mapped[Optional[str]] = mapped_column(String(36))
    locked_revision_id: Mapped[Optional[str]] = mapped_column(String(36))
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "kind", name="uq_study1_shared_artifact_kind"),
    )


class Study1SharedRevisionRow(Base):
    __tablename__ = "study1_shared_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    revision_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    shared_artifact_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_revision_id: Mapped[Optional[str]] = mapped_column(String(36))
    content: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    editor_participant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    editor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "shared_artifact_id",
            "revision_number",
            name="uq_study1_shared_revision_number",
        ),
    )


class Study1SharedConfirmationRow(Base):
    __tablename__ = "study1_shared_confirmations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    confirmation_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    revision_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    participant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "revision_id", "participant_id", name="uq_study1_shared_confirmation_actor"
        ),
    )


class Study1InstrumentDefinitionRow(Base):
    __tablename__ = "study1_instrument_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_definition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    instrument_version: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    applicable_roles: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "instrument_definition_id",
            "instrument_version",
            name="uq_study1_instrument_definition_version",
        ),
    )


class Study1InstrumentItemRow(Base):
    __tablename__ = "study1_instrument_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_definition_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    instrument_version: Mapped[str] = mapped_column(String(64), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    applicable_roles: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response_type: Mapped[str] = mapped_column(String(32), nullable=False)
    response_constraints: Mapped[dict[str, Any]] = mapped_column(JSON_VALUE, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint(
            "instrument_definition_id",
            "instrument_version",
            "item_id",
            name="uq_study1_instrument_item_id",
        ),
        UniqueConstraint(
            "instrument_definition_id",
            "instrument_version",
            "order_index",
            name="uq_study1_instrument_item_order",
        ),
    )


class Study1InstrumentResponseRow(Base):
    __tablename__ = "study1_instrument_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    response_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    participant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    instrument_definition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    instrument_version: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(64), nullable=False)
    ordered_responses: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE, nullable=False)
    response_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "participant_id",
            "instrument_definition_id",
            "instrument_version",
            name="uq_study1_instrument_response_actor",
        ),
    )


class Study1MarkerRow(Base):
    __tablename__ = "study1_markers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    marker_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    marker_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    participant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    participant_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)
    recording_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    marker_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_VALUE, nullable=False
    )

    __table_args__ = (
        Index("ix_study1_markers_session_range", "session_id", "start_ms", "end_ms"),
    )


class Study1ReplayPlanRow(Base):
    __tablename__ = "study1_replay_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    replay_plan_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    context_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    source_marker_ids: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON_VALUE, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    replay_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_VALUE, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "session_id", "version", name="uq_study1_replay_plan_version"
        ),
    )
