"""Domain constants shared by the Study 1 service.

Database rows are added in the authentication/data commits.  Keeping the role
and phase vocabulary here gives the state machine, permissions, routes, export,
and frontend contract one canonical spelling.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Optional

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text, UniqueConstraint, func
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
