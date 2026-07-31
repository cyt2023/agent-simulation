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


class MediaConfigRow(Base):
    __tablename__ = "media_configs"
    __table_args__ = (
        UniqueConstraint("session_id", "phase_version", name="uq_media_config_phase"),
        {"schema": "media"},
    )

    config_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    phase_version: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    config_version: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MediaPhaseSpanRow(Base):
    __tablename__ = "phase_spans"
    __table_args__ = ({"schema": "media"},)

    span_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    phase: Mapped[str] = mapped_column(String(64))
    phase_version: Mapped[int] = mapped_column(Integer)
    room_name: Mapped[str] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MediaAgentTurnRow(Base):
    __tablename__ = "agent_turns"
    __table_args__ = ({"schema": "media"},)

    turn_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    runtime_id: Mapped[str] = mapped_column(String(128), index=True)
    phase_version: Mapped[int] = mapped_column(Integer)
    turn_kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="started")
    context_event_ids: Mapped[list] = mapped_column(JSON, default=list)
    authorized_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    provider_attempt_ids: Mapped[list] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MediaRtcMetricRow(Base):
    __tablename__ = "rtc_metrics"
    __table_args__ = ({"schema": "media"},)

    metric_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    participant_id: Mapped[str] = mapped_column(String(128), index=True)
    role: Mapped[str] = mapped_column(String(32))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class MediaComponentHealthRow(Base):
    __tablename__ = "component_health"
    __table_args__ = ({"schema": "media"},)

    health_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    component: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32))
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class MediaRecordingTrackRow(Base):
    __tablename__ = "recording_tracks"
    __table_args__ = ({"schema": "media"},)

    track_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    runtime_id: Mapped[str] = mapped_column(String(128), index=True)
    participant_id: Mapped[str] = mapped_column(String(128), index=True)
    role: Mapped[str] = mapped_column(String(32))
    room_name: Mapped[str] = mapped_column(String(255))
    room_start_ms: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    codec: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sample_rate_hz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="recording")


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


class MediaSummaryAttemptRow(Base):
    __tablename__ = "summary_attempts"
    __table_args__ = ({"schema": "media"},)

    attempt_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    parent_attempt_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    prompt_version: Mapped[str] = mapped_column(String(128))
    prompt_sha256: Mapped[str] = mapped_column(String(64))
    transcript_checksum: Mapped[str] = mapped_column(String(64))
    config_checksum: Mapped[str] = mapped_column(String(64))
    provider_version: Mapped[str] = mapped_column(String(128))
    sampling: Mapped[dict] = mapped_column(JSON, default=dict)
    input_text: Mapped[str] = mapped_column(Text)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
