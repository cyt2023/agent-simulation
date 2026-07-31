from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class MediaCommandRow(Base):
    __tablename__ = "commands"
    __table_args__ = (
        UniqueConstraint("semantic_key", name="uq_media_command_semantic_key"),
        {"schema": "media"},
    )

    command_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    semantic_key: Mapped[str] = mapped_column(String(512), nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    phase_version: Mapped[int] = mapped_column(Integer)
    command: Mapped[str] = mapped_column(String(64))
    envelope: Mapped[dict] = mapped_column(JSON)
    accepted_response: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(32), default="accepted")
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)


class MediaRuntimeRow(Base):
    __tablename__ = "media_sessions"
    __table_args__ = (
        UniqueConstraint("session_id", "phase_version", "room_kind", name="uq_media_runtime_phase"),
        {"schema": "media"},
    )

    runtime_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    phase_version: Mapped[int] = mapped_column(Integer)
    room_kind: Mapped[str] = mapped_column(String(16))
    room_name: Mapped[str] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    runtime_config: Mapped[dict] = mapped_column(JSON, default=dict)
    recording_root_uri: Mapped[str | None] = mapped_column(Text, nullable=True)


class MediaConnectionRow(Base):
    __tablename__ = "connections"
    __table_args__ = ({"schema": "media"},)

    connection_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    runtime_id: Mapped[str] = mapped_column(String(128), index=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    participant_id: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(32))
    device_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TranscriptSegmentRow(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = ({"schema": "media"},)

    segment_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    runtime_id: Mapped[str] = mapped_column(String(128), index=True)
    speaker: Mapped[str] = mapped_column(String(32))
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_final: Mapped[bool] = mapped_column(default=True)
    provider_version: Mapped[str] = mapped_column(String(128))


class MediaArtifactRow(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("session_id", "kind", "version", name="uq_media_artifact_version"),
        {"schema": "media"},
    )

    artifact_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str] = mapped_column(String(64))
    generator_version: Mapped[str] = mapped_column(String(128))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MediaIncidentRow(Base):
    __tablename__ = "incidents"
    __table_args__ = ({"schema": "media"},)

    incident_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MediaRetentionTombstoneRow(Base):
    __tablename__ = "retention_tombstones"
    __table_args__ = ({"schema": "media"},)

    tombstone_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    retention_job_id: Mapped[str] = mapped_column(String(128), index=True)
    manifest_checksum: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    purged_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutboxMessageRow(Base):
    __tablename__ = "outbox"
    __table_args__ = ({"schema": "media"},)

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    phase_version: Mapped[int] = mapped_column(Integer)
    message_kind: Mapped[str] = mapped_column(String(32), default="event")
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
