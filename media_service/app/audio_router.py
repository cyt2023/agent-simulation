from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import uuid

from .audio import PcmWaveRecorder
from .pipeline import ProxyMediaPipeline
from .voice_activity import VoiceActivityBuffer


@dataclass
class RouterSession:
    runtime_id: str
    artifact_version: str
    accepting_input: bool = True


class AudioPipelineRouter:
    def __init__(
        self,
        pipeline: ProxyMediaPipeline,
        media_root: str | Path,
        *,
        publish_audio: Callable[[str, bytes], Awaitable[None]] | None = None,
    ):
        self.pipeline = pipeline
        self.media_root = Path(media_root)
        self.publish_audio = publish_audio
        self.sessions: dict[str, RouterSession] = {}
        self.detectors: dict[tuple[str, str, str], VoiceActivityBuffer] = {}
        self.recorders: dict[tuple[str, str, str], PcmWaveRecorder] = {}
        self.tasks: dict[str, set[asyncio.Task]] = {}

    async def start_session(
        self,
        session_id: str,
        runtime_id: str,
        context: dict,
        *,
        proxy_enabled: bool,
        artifact_version: str,
    ) -> None:
        self.pipeline.start_session(
            session_id,
            runtime_id,
            context,
            proxy_enabled=proxy_enabled,
            artifact_version=artifact_version,
        )
        self.sessions.setdefault(
            session_id,
            RouterSession(
                runtime_id=runtime_id, artifact_version=artifact_version
            ),
        )
        self.tasks.setdefault(session_id, set())

    def _recorder(
        self, session_id: str, speaker: str, *, sample_rate: int
    ) -> PcmWaveRecorder:
        state = self.sessions[session_id]
        key = (session_id, state.runtime_id, speaker)
        recorder = self.recorders.get(key)
        if not recorder:
            recorder = PcmWaveRecorder(
                self.media_root
                / session_id
                / f"{state.runtime_id}-{speaker}.wav",
                sample_rate=sample_rate,
            )
            self.recorders[key] = recorder
        return recorder

    async def handle_frame(self, session_id: str, speaker: str, frame) -> None:
        state = self.sessions.get(session_id)
        if (
            not state
            or not state.accepting_input
            or speaker not in ("principal", "teammate_1", "teammate_2")
        ):
            return
        pcm = bytes(frame.data)
        self._recorder(
            session_id, speaker, sample_rate=frame.sample_rate
        ).write(pcm)
        key = (session_id, state.runtime_id, speaker)
        detector = self.detectors.setdefault(
            key, VoiceActivityBuffer(sample_rate=frame.sample_rate)
        )
        for utterance in detector.feed(pcm):
            task = asyncio.create_task(
                self.pipeline.process_utterance(
                    session_id,
                    speaker,
                    utterance.pcm_s16le,
                    start_ms=utterance.start_ms,
                    end_ms=utterance.end_ms,
                )
            )
            self.tasks[session_id].add(task)
            task.add_done_callback(self.tasks[session_id].discard)

    async def publish_proxy_audio(self, session_id: str, pcm_s16le: bytes) -> None:
        if session_id not in self.sessions:
            return
        self._recorder(session_id, "proxy", sample_rate=24000).write(pcm_s16le)
        if self.publish_audio:
            await self.publish_audio(session_id, pcm_s16le)

    async def finalize(self, session_id: str, phase_version: int) -> None:
        state = self.sessions.get(session_id)
        if not state:
            return
        state.accepting_input = False
        for (current_session, runtime_id, speaker), detector in list(
            self.detectors.items()
        ):
            if current_session != session_id or runtime_id != state.runtime_id:
                continue
            for utterance in detector.flush():
                task = asyncio.create_task(
                    self.pipeline.process_utterance(
                        session_id,
                        speaker,
                        utterance.pcm_s16le,
                        start_ms=utterance.start_ms,
                        end_ms=utterance.end_ms,
                    )
                )
                self.tasks.setdefault(session_id, set()).add(task)
            self.detectors.pop((current_session, runtime_id, speaker), None)
        pending = list(self.tasks.pop(session_id, set()))
        if pending:
            await asyncio.gather(*pending, return_exceptions=False)
        recording_rows = self._close_recorders(session_id, state.runtime_id)
        try:
            await self.pipeline.finalize(session_id, phase_version)
        finally:
            self._create_manifests(
                session_id, phase_version, state, recording_rows
            )
            self.sessions.pop(session_id, None)

    async def cancel(self, session_id: str) -> None:
        state = self.sessions.pop(session_id, None)
        if not state:
            return
        state.accepting_input = False
        tasks = list(self.tasks.pop(session_id, set()))
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for key in [key for key in self.detectors if key[0] == session_id]:
            self.detectors.pop(key, None)
        self._close_recorders(session_id, state.runtime_id)
        self.pipeline.cancel_session(session_id)

    def _close_recorders(self, session_id: str, runtime_id: str) -> list[dict]:
        rows: list[dict] = []
        for key, recorder in list(self.recorders.items()):
            if key[:2] != (session_id, runtime_id):
                continue
            recorder.close()
            payload = recorder.path.read_bytes()
            rows.append(
                {
                    "recording_id": recorder.path.name,
                    "runtime_id": runtime_id,
                    "speaker": key[2],
                    "content_type": "audio/wav",
                    "size": len(payload),
                    "checksum": hashlib.sha256(payload).hexdigest(),
                }
            )
            self.recorders.pop(key, None)
        return sorted(rows, key=lambda row: row["speaker"])

    def _create_manifests(
        self,
        session_id: str,
        phase_version: int,
        state: RouterSession,
        recordings: list[dict],
    ) -> None:
        agent_log = [
            {
                "segment_id": row.segment_id,
                "start_ms": row.start_ms,
                "end_ms": row.end_ms,
                "text": row.text,
                "provider_version": row.provider_version,
            }
            for row in self.pipeline.repository.list_session_segments(session_id)
            if row.runtime_id == state.runtime_id and row.speaker == "proxy"
        ]
        for kind, value in (
            ("recording_manifest", recordings),
            ("agent_log_manifest", agent_log),
        ):
            content = json.dumps(value, ensure_ascii=False, sort_keys=True)
            self.pipeline.repository.create_artifact_and_enqueue(
                phase_version=phase_version,
                artifact_id=str(uuid.uuid4()),
                session_id=session_id,
                kind=kind,
                version=state.artifact_version,
                content=content,
                storage_uri=None,
                checksum=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                generator_version="study1-media-runtime-v1",
                metadata={"runtime_id": state.runtime_id},
            )

    async def regenerate_summary(
        self, session_id: str, phase_version: int, payload: dict
    ) -> None:
        await self.pipeline.regenerate_summary(
            session_id,
            phase_version=phase_version,
            reason=str(payload["reason"]),
            source_transcript_checksum=str(payload["source_transcript_checksum"]),
            source_summary_version=str(payload["source_summary_version"]),
        )
