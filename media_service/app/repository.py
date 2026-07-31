from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from .db import Database
from .models import (
    MediaArtifactRow,
    MediaCommandRow,
    MediaConnectionRow,
    MediaAgentTurnRow,
    MediaConfigRow,
    MediaIncidentRow,
    MediaComponentHealthRow,
    MediaRecordingTrackRow,
    MediaRetentionTombstoneRow,
    MediaRtcMetricRow,
    MediaRuntimeRow,
    MediaSummaryAttemptRow,
    OutboxMessageRow,
    TranscriptSegmentRow,
)
from .schemas import CommandEnvelope, RuntimeState


@dataclass(frozen=True)
class AcceptedCommand:
    accepted: bool
    duplicate: bool
    command_id: str
    runtime_state: RuntimeState


class MediaRepository:
    def __init__(self, database: Database):
        self.database = database

    def accept_command(
        self, command: CommandEnvelope, semantic_key: str, state: RuntimeState = RuntimeState.PREPARING
    ) -> AcceptedCommand:
        try:
            with self.database.session_factory.begin() as session:
                existing = session.scalar(
                    select(MediaCommandRow).where(
                        (MediaCommandRow.command_id == command.command_id)
                        | (MediaCommandRow.semantic_key == semantic_key)
                    )
                )
                if existing:
                    return self._duplicate_acceptance(existing)
                response = {
                    "accepted": True,
                    "duplicate": False,
                    "command_id": command.command_id,
                    "runtime_state": state.value,
                }
                session.add(
                    MediaCommandRow(
                        command_id=command.command_id,
                        semantic_key=semantic_key,
                        session_id=command.session_id,
                        phase_version=command.phase_version,
                        command=command.command.value,
                        envelope=command.model_dump(mode="json"),
                        accepted_response=response,
                    )
                )
                session.flush()
                return AcceptedCommand(
                    accepted=True,
                    duplicate=False,
                    command_id=command.command_id,
                    runtime_state=state,
                )
        except IntegrityError:
            with self.database.session_factory() as session:
                existing = session.scalar(
                    select(MediaCommandRow).where(
                        (MediaCommandRow.command_id == command.command_id)
                        | (MediaCommandRow.semantic_key == semantic_key)
                    )
                )
                if not existing:
                    raise
                return self._duplicate_acceptance(existing)

    def get_command(self, command_id: str) -> MediaCommandRow:
        with self.database.session_factory() as session:
            row = session.get(MediaCommandRow, command_id)
            if not row:
                raise KeyError(command_id)
            return row

    def pending_commands(self) -> list[MediaCommandRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaCommandRow)
                    .where(MediaCommandRow.status.in_(("accepted", "failed")))
                    .order_by(MediaCommandRow.received_at)
                ).all()
            )

    def requeue_interrupted_commands(self) -> int:
        """Return commands left processing by a previous process to the queue."""
        with self.database.session_factory.begin() as session:
            result = session.execute(
                update(MediaCommandRow)
                .where(MediaCommandRow.status == "processing")
                .values(status="accepted", error_code="PROCESS_RESTARTED")
            )
            return int(result.rowcount or 0)

    def claim_command(self, command_id: str) -> bool:
        """Atomically lease an executable command to exactly one worker."""
        with self.database.session_factory.begin() as session:
            result = session.execute(
                update(MediaCommandRow)
                .where(
                    MediaCommandRow.command_id == command_id,
                    MediaCommandRow.status.in_(("accepted", "failed")),
                )
                .values(status="processing", error_code=None)
            )
            return int(result.rowcount or 0) == 1

    def mark_command_status(
        self, command_id: str, status: str, *, error_code: str | None = None
    ) -> MediaCommandRow:
        with self.database.session_factory.begin() as session:
            row = session.get(MediaCommandRow, command_id)
            if not row:
                raise KeyError(command_id)
            row.status = status
            row.error_code = error_code
            return row

    @staticmethod
    def _duplicate_acceptance(existing: MediaCommandRow) -> AcceptedCommand:
        response = existing.accepted_response
        return AcceptedCommand(
            accepted=bool(response["accepted"]),
            duplicate=True,
            command_id=existing.command_id,
            runtime_state=RuntimeState(response["runtime_state"]),
        )

    def enqueue_event(
        self,
        session_id: str,
        phase_version: int,
        event_type: str,
        payload: dict,
    ) -> OutboxMessageRow:
        row = OutboxMessageRow(
            event_id=str(uuid.uuid4()),
            session_id=session_id,
            phase_version=phase_version,
            event_type=event_type,
            payload=payload,
        )
        with self.database.session_factory.begin() as session:
            session.add(row)
        return row

    def enqueue_artifact(
        self, session_id: str, phase_version: int, artifact: MediaArtifactRow
    ) -> OutboxMessageRow:
        row = OutboxMessageRow(
            event_id=str(uuid.uuid4()),
            session_id=session_id,
            phase_version=phase_version,
            message_kind="artifact",
            event_type=artifact.kind,
            payload={
                "artifact_id": artifact.artifact_id,
                "type": artifact.kind,
                "version": artifact.version,
                "content": artifact.content,
                "storage_uri": artifact.storage_uri,
                "checksum": artifact.checksum,
                "created_at": artifact.created_at.isoformat().replace("+00:00", "Z"),
                "generator_version": artifact.generator_version,
                "metadata": artifact.metadata_json,
            },
        )
        with self.database.session_factory.begin() as session:
            session.add(row)
        return row

    def add_transcript_segment(
        self,
        *,
        segment_id: str,
        session_id: str,
        runtime_id: str,
        speaker: str,
        start_ms: int,
        end_ms: int,
        text: str,
        confidence: float | None,
        is_final: bool,
        provider_version: str,
    ) -> TranscriptSegmentRow:
        row = TranscriptSegmentRow(
            segment_id=segment_id,
            session_id=session_id,
            runtime_id=runtime_id,
            speaker=speaker,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            confidence=confidence,
            is_final=is_final,
            provider_version=provider_version,
        )
        with self.database.session_factory.begin() as session:
            session.add(row)
        return row

    def record_connection(
        self,
        *,
        session_id: str,
        runtime_id: str,
        participant_id: str,
        role: str,
        state: str,
        device_metadata: dict,
    ) -> MediaConnectionRow:
        row = MediaConnectionRow(
            connection_id=str(uuid.uuid4()),
            runtime_id=runtime_id,
            session_id=session_id,
            participant_id=participant_id,
            role=role,
            state=state,
            device_metadata=device_metadata,
        )
        with self.database.session_factory.begin() as session:
            session.add(row)
        return row

    def create_artifact(
        self,
        *,
        artifact_id: str,
        session_id: str,
        kind: str,
        version: str,
        content: str | None,
        storage_uri: str | None,
        checksum: str,
        generator_version: str,
        metadata: dict,
    ) -> MediaArtifactRow:
        row = MediaArtifactRow(
            artifact_id=artifact_id,
            session_id=session_id,
            kind=kind,
            version=version,
            content=content,
            storage_uri=storage_uri,
            checksum=checksum,
            generator_version=generator_version,
            metadata_json=metadata,
        )
        with self.database.session_factory.begin() as session:
            session.add(row)
        return row

    def create_artifact_and_enqueue(
        self,
        *,
        phase_version: int,
        artifact_id: str,
        session_id: str,
        kind: str,
        version: str,
        content: str | None,
        storage_uri: str | None,
        checksum: str,
        generator_version: str,
        metadata: dict,
    ) -> MediaArtifactRow:
        with self.database.session_factory.begin() as session:
            artifact = session.scalar(
                select(MediaArtifactRow).where(
                    MediaArtifactRow.session_id == session_id,
                    MediaArtifactRow.kind == kind,
                    MediaArtifactRow.version == version,
                )
            )
            if artifact:
                if artifact.checksum != checksum:
                    raise ValueError(
                        f"Artifact {kind}:{version} already exists with a different checksum"
                    )
                return artifact
            artifact = MediaArtifactRow(
                artifact_id=artifact_id,
                session_id=session_id,
                kind=kind,
                version=version,
                content=content,
                storage_uri=storage_uri,
                checksum=checksum,
                generator_version=generator_version,
                metadata_json=metadata,
            )
            session.add(artifact)
            session.flush()
            session.add(
                OutboxMessageRow(
                    event_id=str(uuid.uuid4()),
                    session_id=session_id,
                    phase_version=phase_version,
                    message_kind="artifact",
                    event_type=kind,
                    payload={
                        "artifact_id": artifact.artifact_id,
                        "type": artifact.kind,
                        "version": artifact.version,
                        "content": artifact.content,
                        "storage_uri": artifact.storage_uri,
                        "checksum": artifact.checksum,
                        "created_at": artifact.created_at.isoformat().replace(
                            "+00:00", "Z"
                        ),
                        "generator_version": artifact.generator_version,
                        "metadata": artifact.metadata_json,
                    },
                )
            )
            return artifact

    def get_or_create_runtime(
        self,
        *,
        runtime_id: str,
        session_id: str,
        phase_version: int,
        room_kind: str,
        room_name: str,
        state: RuntimeState,
        runtime_config: dict,
    ) -> tuple[MediaRuntimeRow, bool]:
        with self.database.session_factory.begin() as session:
            existing = session.scalar(
                select(MediaRuntimeRow).where(
                    MediaRuntimeRow.session_id == session_id,
                    MediaRuntimeRow.phase_version == phase_version,
                    MediaRuntimeRow.room_kind == room_kind,
                )
            )
            if existing:
                return existing, False
            row = MediaRuntimeRow(
                runtime_id=runtime_id,
                session_id=session_id,
                phase_version=phase_version,
                room_kind=room_kind,
                room_name=room_name,
                state=state.value,
                runtime_config=runtime_config,
                started_at=datetime.now(timezone.utc),
            )
            session.add(row)
            return row, True

    def active_runtime(self, session_id: str) -> MediaRuntimeRow | None:
        terminal = (RuntimeState.STOPPED.value, RuntimeState.ERROR.value)
        with self.database.session_factory() as session:
            return session.scalar(
                select(MediaRuntimeRow)
                .where(
                    MediaRuntimeRow.session_id == session_id,
                    MediaRuntimeRow.state.not_in(terminal),
                )
                .order_by(MediaRuntimeRow.started_at.desc())
            )

    def update_runtime_state(
        self, runtime_id: str, state: RuntimeState, *, ended: bool = False
    ) -> MediaRuntimeRow:
        with self.database.session_factory.begin() as session:
            row = session.get(MediaRuntimeRow, runtime_id)
            if not row:
                raise KeyError(runtime_id)
            row.state = state.value
            if ended:
                row.ended_at = datetime.now(timezone.utc)
            return row

    def mark_runtime_handoff(
        self, runtime_id: str, phase_version: int
    ) -> MediaRuntimeRow:
        with self.database.session_factory.begin() as session:
            row = session.get(MediaRuntimeRow, runtime_id)
            if not row:
                raise KeyError(runtime_id)
            row.state = RuntimeState.HANDING_OFF.value
            row.runtime_config = {
                **(row.runtime_config or {}),
                "handoff_phase_version": phase_version,
                "proxy_stopped_at": (row.runtime_config or {}).get(
                    "proxy_stopped_at"
                )
                or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            return row

    def patch_runtime_config(
        self, runtime_id: str, values: dict
    ) -> MediaRuntimeRow:
        with self.database.session_factory.begin() as session:
            row = session.get(MediaRuntimeRow, runtime_id)
            if not row:
                raise KeyError(runtime_id)
            row.runtime_config = {**(row.runtime_config or {}), **values}
            return row

    def finish_session_runtimes(
        self, session_id: str, state: RuntimeState = RuntimeState.STOPPED
    ) -> list[MediaRuntimeRow]:
        with self.database.session_factory.begin() as session:
            rows = list(
                session.scalars(
                    select(MediaRuntimeRow).where(
                        MediaRuntimeRow.session_id == session_id,
                        MediaRuntimeRow.ended_at.is_(None),
                    )
                ).all()
            )
            ended_at = datetime.now(timezone.utc)
            for row in rows:
                row.state = state.value
                row.ended_at = ended_at
            return rows

    def finish_runtime_with_event(
        self,
        runtime_id: str,
        *,
        state: RuntimeState,
        session_id: str,
        phase_version: int,
        event_type: str,
        payload: dict,
        runtime_config_patch: dict | None = None,
    ) -> MediaRuntimeRow:
        return self._write_runtime_event(
            runtime_id,
            state=state,
            session_id=session_id,
            phase_version=phase_version,
            event_type=event_type,
            payload=payload,
            ended=True,
            runtime_config_patch=runtime_config_patch,
        )

    def transition_runtime_with_event(
        self,
        runtime_id: str,
        *,
        state: RuntimeState,
        session_id: str,
        phase_version: int,
        event_type: str,
        payload: dict,
        runtime_config_patch: dict | None = None,
    ) -> MediaRuntimeRow:
        return self._write_runtime_event(
            runtime_id,
            state=state,
            session_id=session_id,
            phase_version=phase_version,
            event_type=event_type,
            payload=payload,
            ended=False,
            runtime_config_patch=runtime_config_patch,
        )

    def _write_runtime_event(
        self,
        runtime_id: str,
        *,
        state: RuntimeState,
        session_id: str,
        phase_version: int,
        event_type: str,
        payload: dict,
        ended: bool,
        runtime_config_patch: dict | None = None,
    ) -> MediaRuntimeRow:
        event_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"study1-media:{runtime_id}:{phase_version}:{event_type}",
            )
        )

        def update_runtime(session):
            runtime = session.get(MediaRuntimeRow, runtime_id)
            if not runtime:
                raise KeyError(runtime_id)
            runtime.state = state.value
            if ended:
                runtime.ended_at = runtime.ended_at or datetime.now(timezone.utc)
            if runtime_config_patch:
                runtime.runtime_config = {
                    **(runtime.runtime_config or {}),
                    **runtime_config_patch,
                }
            return runtime

        try:
            with self.database.session_factory.begin() as session:
                runtime = update_runtime(session)
                if session.get(OutboxMessageRow, event_id) is None:
                    session.add(
                        OutboxMessageRow(
                            event_id=event_id,
                            session_id=session_id,
                            phase_version=phase_version,
                            event_type=event_type,
                            payload=payload,
                        )
                    )
                return runtime
        except IntegrityError:
            # A competing process committed the deterministic event first.
            with self.database.session_factory.begin() as session:
                if session.get(OutboxMessageRow, event_id) is None:
                    raise
                return update_runtime(session)

    def mark_outbox_attempt(self, event_id: str, error: str) -> None:
        with self.database.session_factory.begin() as session:
            row = session.get(OutboxMessageRow, event_id)
            if not row:
                raise KeyError(event_id)
            row.attempt_count += 1
            row.last_error = error

    def mark_outbox_delivered(self, event_id: str) -> None:
        with self.database.session_factory.begin() as session:
            row = session.get(OutboxMessageRow, event_id)
            if not row:
                raise KeyError(event_id)
            row.delivered_at = datetime.now(timezone.utc)
            row.last_error = None

    def mark_outbox_discarded(self, event_id: str, reason: str) -> None:
        with self.database.session_factory.begin() as session:
            row = session.get(OutboxMessageRow, event_id)
            if not row:
                raise KeyError(event_id)
            row.attempt_count += 1
            row.last_error = reason
            row.delivered_at = datetime.now(timezone.utc)

    def pending_outbox(self) -> list[OutboxMessageRow]:
        with self.database.session_factory() as session:
            rows = session.scalars(
                select(OutboxMessageRow)
                .where(OutboxMessageRow.delivered_at.is_(None))
                .order_by(OutboxMessageRow.occurred_at)
            ).all()
            return list(rows)

    def list_session_outbox(self, session_id: str) -> list[OutboxMessageRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(OutboxMessageRow)
                    .where(OutboxMessageRow.session_id == session_id)
                    .order_by(OutboxMessageRow.occurred_at)
                ).all()
            )

    def list_session_commands(self, session_id: str) -> list[MediaCommandRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaCommandRow)
                    .where(MediaCommandRow.session_id == session_id)
                    .order_by(MediaCommandRow.received_at)
                ).all()
            )

    def list_session_runtimes(self, session_id: str) -> list[MediaRuntimeRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaRuntimeRow)
                    .where(MediaRuntimeRow.session_id == session_id)
                    .order_by(MediaRuntimeRow.started_at)
                ).all()
            )

    def nonterminal_runtimes(self) -> list[MediaRuntimeRow]:
        terminal = (RuntimeState.STOPPED.value, RuntimeState.ERROR.value)
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaRuntimeRow)
                    .where(MediaRuntimeRow.state.not_in(terminal))
                    .order_by(MediaRuntimeRow.started_at)
                ).all()
            )

    def list_session_connections(self, session_id: str) -> list[MediaConnectionRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaConnectionRow)
                    .where(MediaConnectionRow.session_id == session_id)
                    .order_by(MediaConnectionRow.occurred_at)
                ).all()
            )

    def list_session_recording_tracks(
        self, session_id: str
    ) -> list[MediaRecordingTrackRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaRecordingTrackRow)
                    .where(MediaRecordingTrackRow.session_id == session_id)
                    .order_by(
                        MediaRecordingTrackRow.room_start_ms,
                        MediaRecordingTrackRow.track_id,
                    )
                ).all()
            )

    def preflight_ready_roles(self, session_id: str) -> set[str]:
        latest: dict[str, MediaConnectionRow] = {}
        for row in self.list_session_connections(session_id):
            if row.runtime_id.startswith("preflight:"):
                latest[row.role] = row
        return {role for role, row in latest.items() if row.state == "ready"}

    def list_session_segments(self, session_id: str) -> list[TranscriptSegmentRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(TranscriptSegmentRow)
                    .where(TranscriptSegmentRow.session_id == session_id)
                    .order_by(TranscriptSegmentRow.start_ms)
                ).all()
            )

    def list_session_artifacts(self, session_id: str) -> list[MediaArtifactRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaArtifactRow)
                    .where(MediaArtifactRow.session_id == session_id)
                    .order_by(MediaArtifactRow.created_at)
                ).all()
            )

    def list_session_incidents(self, session_id: str) -> list[MediaIncidentRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaIncidentRow)
                    .where(MediaIncidentRow.session_id == session_id)
                    .order_by(MediaIncidentRow.created_at)
                ).all()
            )

    def store_media_config(
        self, *, session_id: str, phase_version: int, checksum: str, payload: dict
    ) -> MediaConfigRow:
        row = MediaConfigRow(
            config_id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"study1-media-config:{session_id}:{phase_version}:{checksum}",
                )
            ),
            session_id=session_id,
            phase_version=phase_version,
            checksum=checksum,
            config_version=str(payload.get("config_version") or "study1-media-config-v2"),
            payload=payload,
        )
        with self.database.session_factory.begin() as session:
            existing = session.get(MediaConfigRow, row.config_id)
            if existing:
                return existing
            session.add(row)
            return row

    def begin_agent_turn(self, payload: dict) -> MediaAgentTurnRow:
        context_event_ids = list(payload.get("context_event_ids") or [])
        if not context_event_ids:
            raise ValueError("Agent turns require context_event_ids before provider attempts")
        row = MediaAgentTurnRow(
            turn_id=str(payload.get("turn_id") or uuid.uuid4()),
            session_id=str(payload["session_id"]),
            runtime_id=str(payload["runtime_id"]),
            phase_version=int(payload["phase_version"]),
            turn_kind=str(payload.get("turn_kind") or "llm_response"),
            status="started",
            context_event_ids=context_event_ids,
            authorized_snapshot=dict(payload.get("authorized_snapshot") or {}),
            provider_attempt_ids=list(payload.get("provider_attempt_ids") or []),
        )
        with self.database.session_factory.begin() as session:
            existing = session.get(MediaAgentTurnRow, row.turn_id)
            if existing:
                return existing
            session.add(row)
            return row

    def finish_agent_turn(
        self,
        turn_id: str,
        *,
        status: str,
        provider_attempt_id: str | None = None,
        error_code: str | None = None,
    ) -> MediaAgentTurnRow:
        with self.database.session_factory.begin() as session:
            row = session.get(MediaAgentTurnRow, turn_id)
            if not row:
                raise KeyError(turn_id)
            attempts = list(row.provider_attempt_ids or [])
            if provider_attempt_id:
                attempts.append(provider_attempt_id)
            row.provider_attempt_ids = attempts
            row.status = status
            row.error_code = error_code
            row.ended_at = datetime.now(timezone.utc)
            return row

    def list_session_agent_turns(self, session_id: str) -> list[MediaAgentTurnRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaAgentTurnRow)
                    .where(MediaAgentTurnRow.session_id == session_id)
                    .order_by(MediaAgentTurnRow.started_at)
                ).all()
            )

    def begin_summary_attempt(
        self,
        *,
        attempt_id: str,
        session_id: str,
        parent_attempt_id: str | None,
        prompt_version: str,
        prompt_sha256: str,
        transcript_checksum: str,
        config_checksum: str,
        provider_version: str,
        sampling: dict,
        input_text: str,
        reason: str | None = None,
    ) -> MediaSummaryAttemptRow:
        row = MediaSummaryAttemptRow(
            attempt_id=attempt_id,
            session_id=session_id,
            parent_attempt_id=parent_attempt_id,
            status="started",
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
            transcript_checksum=transcript_checksum,
            config_checksum=config_checksum,
            provider_version=provider_version,
            sampling=sampling,
            input_text=input_text,
            reason=reason,
        )
        with self.database.session_factory.begin() as session:
            session.add(row)
        return row

    def record_rtc_metric(
        self,
        *,
        session_id: str,
        participant_id: str,
        role: str,
        observed_at: datetime,
        payload: dict,
    ) -> MediaRtcMetricRow:
        row = MediaRtcMetricRow(
            metric_id=str(uuid.uuid4()),
            session_id=session_id,
            participant_id=participant_id,
            role=role,
            observed_at=observed_at,
            payload=payload,
        )
        with self.database.session_factory.begin() as session:
            session.add(row)
        return row

    def list_session_rtc_metrics(self, session_id: str) -> list[MediaRtcMetricRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaRtcMetricRow)
                    .where(MediaRtcMetricRow.session_id == session_id)
                    .order_by(MediaRtcMetricRow.observed_at, MediaRtcMetricRow.metric_id)
                ).all()
            )

    def record_component_health(
        self,
        *,
        component: str,
        status: str,
        latency_ms: float | None = None,
        error_code: str | None = None,
        observed_at: datetime | None = None,
        payload: dict | None = None,
    ) -> MediaComponentHealthRow:
        row = MediaComponentHealthRow(
            health_id=str(uuid.uuid4()),
            component=component,
            status=status,
            latency_ms=latency_ms,
            error_code=error_code,
            observed_at=observed_at or datetime.now(timezone.utc),
            payload=payload or {},
        )
        with self.database.session_factory.begin() as session:
            session.add(row)
        return row

    def list_component_health(self) -> list[MediaComponentHealthRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaComponentHealthRow).order_by(
                        MediaComponentHealthRow.observed_at,
                        MediaComponentHealthRow.health_id,
                    )
                ).all()
            )

    def recording_track_started(
        self,
        *,
        track_id: str,
        session_id: str,
        runtime_id: str,
        participant_id: str,
        role: str,
        room_name: str,
        clock_id: str,
        room_start_ms: int,
        started_at: datetime,
        codec: str,
        sample_rate_hz: int,
        content_type: str,
        consent_scope: str,
    ) -> MediaRecordingTrackRow:
        row = MediaRecordingTrackRow(
            track_id=track_id,
            session_id=session_id,
            runtime_id=runtime_id,
            participant_id=participant_id,
            role=role,
            room_name=room_name,
            clock_id=clock_id,
            room_start_ms=room_start_ms,
            started_at=started_at,
            codec=codec,
            sample_rate_hz=sample_rate_hz,
            content_type=content_type,
            consent_scope=consent_scope,
            status="recording",
        )
        with self.database.session_factory.begin() as session:
            existing = session.get(MediaRecordingTrackRow, track_id)
            if existing:
                return existing
            session.add(row)
            return row

    def recording_track_finished(
        self,
        track_id: str,
        *,
        room_end_ms: int,
        ended_at: datetime,
        checksum: str,
        storage_uri: str,
        size_bytes: int,
        duration_ms: int,
        status: str = "complete",
    ) -> MediaRecordingTrackRow:
        with self.database.session_factory.begin() as session:
            row = session.get(MediaRecordingTrackRow, track_id)
            if not row:
                raise KeyError(track_id)
            row.room_end_ms = room_end_ms
            row.ended_at = ended_at
            row.checksum = checksum
            row.storage_uri = storage_uri
            row.size_bytes = size_bytes
            row.duration_ms = duration_ms
            row.status = status
            return row

    def finish_summary_attempt(
        self,
        attempt_id: str,
        *,
        status: str,
        output_text: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> MediaSummaryAttemptRow:
        with self.database.session_factory.begin() as session:
            row = session.get(MediaSummaryAttemptRow, attempt_id)
            if not row:
                raise KeyError(attempt_id)
            row.status = status
            row.output_text = output_text
            row.error_code = error_code
            row.error_message = error_message
            row.ended_at = datetime.now(timezone.utc)
            return row

    def get_summary_attempt(self, attempt_id: str) -> MediaSummaryAttemptRow:
        with self.database.session_factory() as session:
            row = session.get(MediaSummaryAttemptRow, attempt_id)
            if not row:
                raise KeyError(attempt_id)
            return row

    def list_session_summary_attempts(
        self, session_id: str
    ) -> list[MediaSummaryAttemptRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaSummaryAttemptRow)
                    .where(MediaSummaryAttemptRow.session_id == session_id)
                    .order_by(MediaSummaryAttemptRow.started_at)
                ).all()
            )

    def purge_session_media(
        self,
        session_id: str,
        *,
        retention_job_id: str,
        manifest_checksum: str,
        reason: str,
        phase_version: int = 1,
    ) -> MediaRetentionTombstoneRow:
        tombstone_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"study1-media-retention:{session_id}:{retention_job_id}",
            )
        )
        event_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"study1-media-purged:{session_id}:{retention_job_id}:{manifest_checksum}",
            )
        )
        with self.database.session_factory.begin() as session:
            existing = session.get(MediaRetentionTombstoneRow, tombstone_id)
            if existing:
                return existing
            purged_counts = {
                "transcript_segments": len(
                    session.scalars(
                        select(TranscriptSegmentRow).where(
                            TranscriptSegmentRow.session_id == session_id
                        )
                    ).all()
                ),
                "artifacts": len(
                    session.scalars(
                        select(MediaArtifactRow).where(
                            MediaArtifactRow.session_id == session_id
                        )
                    ).all()
                ),
                "incidents": len(
                    session.scalars(
                        select(MediaIncidentRow).where(
                            MediaIncidentRow.session_id == session_id
                        )
                    ).all()
                ),
            }
            session.execute(
                delete(TranscriptSegmentRow).where(
                    TranscriptSegmentRow.session_id == session_id
                )
            )
            session.execute(
                delete(MediaArtifactRow).where(MediaArtifactRow.session_id == session_id)
            )
            session.execute(
                delete(MediaIncidentRow).where(MediaIncidentRow.session_id == session_id)
            )
            tombstone = MediaRetentionTombstoneRow(
                tombstone_id=tombstone_id,
                session_id=session_id,
                retention_job_id=retention_job_id,
                manifest_checksum=manifest_checksum,
                reason=reason,
                purged_counts=purged_counts,
            )
            session.add(tombstone)
            if session.get(OutboxMessageRow, event_id) is None:
                session.add(
                    OutboxMessageRow(
                        event_id=event_id,
                        session_id=session_id,
                        phase_version=max(1, int(phase_version or 1)),
                        event_type="MEDIA_PURGED",
                        payload={
                            "retention_job_id": retention_job_id,
                            "manifest_checksum": manifest_checksum,
                            "purged_counts": purged_counts,
                        },
                    )
                )
            return tombstone

    def list_session_retention_tombstones(
        self, session_id: str
    ) -> list[MediaRetentionTombstoneRow]:
        with self.database.session_factory() as session:
            return list(
                session.scalars(
                    select(MediaRetentionTombstoneRow)
                    .where(MediaRetentionTombstoneRow.session_id == session_id)
                    .order_by(MediaRetentionTombstoneRow.created_at)
                ).all()
            )
