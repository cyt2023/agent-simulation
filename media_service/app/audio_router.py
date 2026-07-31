from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any
import uuid
import wave

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
        begin_proxy_audio: Callable[[str, str], Any] | None = None,
        interrupt_proxy_audio: Callable[[str], Awaitable[Any]] | None = None,
    ):
        self.pipeline = pipeline
        self.media_root = Path(media_root)
        self.publish_audio = publish_audio
        self.begin_proxy_audio_callback = begin_proxy_audio
        self.interrupt_proxy_audio_callback = interrupt_proxy_audio
        self._publish_accepts_generation = _accepts_keyword(
            publish_audio, "generation"
        )
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
        was_speaking = detector.start_ms is not None
        utterances = detector.feed(pcm)
        if not was_speaking and detector.start_ms is not None:
            interrupt = getattr(self.pipeline, "interrupt", None)
            if interrupt:
                interrupted = interrupt(session_id, speaker)
                if interrupted:
                    await self.interrupt_proxy_audio(session_id)
        for utterance in utterances:
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

    def begin_proxy_playback(self, session_id: str, turn_id: str):
        if not self.begin_proxy_audio_callback:
            return None
        return self.begin_proxy_audio_callback(session_id, turn_id)

    async def interrupt_proxy_audio(self, session_id: str):
        if not self.interrupt_proxy_audio_callback:
            return False
        return await _maybe_await(self.interrupt_proxy_audio_callback(session_id))

    async def publish_proxy_audio(
        self, session_id: str, pcm_s16le: bytes, *, generation=None
    ) -> bool:
        if session_id not in self.sessions:
            return False
        if self.publish_audio:
            if generation is not None and self._publish_accepts_generation:
                published = await self.publish_audio(
                    session_id, pcm_s16le, generation=generation
                )
            else:
                published = await self.publish_audio(session_id, pcm_s16le)
            if published is False:
                return False
        self._recorder(session_id, "proxy", sample_rate=24000).write(pcm_s16le)
        return True

    async def finalize(self, session_id: str, phase_version: int) -> None:
        state = self.sessions.get(session_id)
        if not state:
            return
        state.accepting_input = False
        first_error: BaseException | None = None
        recording_rows: list[dict] = []

        def remember(error: BaseException) -> None:
            nonlocal first_error
            if first_error is None:
                first_error = error

        try:
            for (current_session, runtime_id, speaker), detector in list(
                self.detectors.items()
            ):
                if current_session != session_id or runtime_id != state.runtime_id:
                    continue
                try:
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
                except BaseException as error:
                    remember(error)
                finally:
                    self.detectors.pop((current_session, runtime_id, speaker), None)

            pending = list(self.tasks.pop(session_id, set()))
            if pending:
                try:
                    results = await asyncio.gather(*pending, return_exceptions=True)
                    for result in results:
                        if isinstance(result, BaseException):
                            remember(result)
                except BaseException as error:
                    remember(error)

            try:
                recording_rows = self._close_recorders(
                    session_id, state.runtime_id
                )
            except BaseException as error:
                remember(error)

            try:
                await self.pipeline.finalize(session_id, phase_version)
            except BaseException as error:
                remember(error)

            try:
                self._create_manifests(
                    session_id, phase_version, state, recording_rows
                )
            except BaseException as error:
                remember(error)
        finally:
            self.sessions.pop(session_id, None)
            self.tasks.pop(session_id, None)
            for key in [key for key in self.detectors if key[0] == session_id]:
                self.detectors.pop(key, None)
            for key, recorder in list(self.recorders.items()):
                if key[0] != session_id:
                    continue
                self.recorders.pop(key, None)
                try:
                    recorder.close()
                except BaseException as error:
                    remember(error)
            try:
                self.pipeline.cancel_session(session_id)
            except BaseException as error:
                remember(error)

        if first_error is not None:
            raise first_error

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
        first_error: BaseException | None = None
        for key, recorder in list(self.recorders.items()):
            if key[:2] != (session_id, runtime_id):
                continue
            self.recorders.pop(key, None)
            try:
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
                        "duration_ms": _wave_duration_ms(recorder.path),
                        "consent_scope": "study1_audio_recording_and_research_export",
                    }
                )
            except BaseException as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error
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
        pipeline_log = getattr(self.pipeline, "agent_log", None)
        if pipeline_log:
            agent_log.extend(pipeline_log(session_id, state.runtime_id))
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


def _wave_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as stream:
        frame_rate = stream.getframerate()
        return round(stream.getnframes() * 1000 / frame_rate) if frame_rate else 0


def _accepts_keyword(callback, keyword: str) -> bool:
    if not callback:
        return False
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        or parameter.name == keyword
        for parameter in signature.parameters.values()
    )


async def _maybe_await(result):
    if inspect.isawaitable(result):
        return await result
    return result
