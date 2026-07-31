from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from media_service.app.audio_router import AudioPipelineRouter
from media_service.app.playback import ProxyPlaybackController


class StubPipeline:
    def __init__(self, repository):
        self.repository = repository
        self.sessions = {}
        self.cancelled = []

    def start_session(
        self,
        session_id,
        runtime_id,
        context,
        *,
        proxy_enabled,
        artifact_version,
    ):
        self.sessions[session_id] = runtime_id

    async def process_utterance(self, *args, **kwargs):
        pass

    async def finalize(self, session_id, phase_version):
        pass

    def cancel_session(self, session_id):
        self.cancelled.append(session_id)
        self.sessions.pop(session_id, None)

    async def regenerate_summary(self, *args, **kwargs):
        pass


@pytest.mark.asyncio
async def test_barge_in_clears_queue_and_rejects_late_frames():
    audio_source = SimpleNamespace(
        clear_queue=AsyncMock(),
        capture_frame=AsyncMock(),
    )
    playback = ProxyPlaybackController(audio_source)

    generation = playback.begin("turn-1")
    await playback.interrupt(generation)
    published = await playback.publish(generation, b"late")

    assert published is False
    assert audio_source.clear_queue.await_count == 1
    assert audio_source.capture_frame.await_count == 0


@pytest.mark.asyncio
async def test_router_clears_proxy_audio_when_human_barge_in_starts(repository, tmp_path):
    interrupts = []
    cleared = []

    class InterruptiblePipeline(StubPipeline):
        def interrupt(self, session_id, speaker):
            interrupts.append((session_id, speaker))
            return True

    async def interrupt_proxy_audio(session_id):
        cleared.append(session_id)

    router = AudioPipelineRouter(
        InterruptiblePipeline(repository),
        tmp_path,
        interrupt_proxy_audio=interrupt_proxy_audio,
    )
    await router.start_session(
        "session-1",
        "runtime-1",
        {},
        proxy_enabled=True,
        artifact_version="1",
    )

    loud_300ms = b"\xff\x7f" * 14400
    frame = SimpleNamespace(data=loud_300ms, sample_rate=48000)
    await router.handle_frame("session-1", "teammate_1", frame)

    assert interrupts == [("session-1", "teammate_1")]
    assert cleared == ["session-1"]


@pytest.mark.asyncio
async def test_router_records_human_and_proxy_tracks_and_emits_manifests(
    repository, tmp_path
):
    published = []

    async def publish(session_id, chunk):
        published.append((session_id, chunk))

    pipeline = StubPipeline(repository)
    router = AudioPipelineRouter(
        pipeline, tmp_path, publish_audio=publish
    )
    await router.start_session(
        "session-1",
        "runtime-1",
        {},
        proxy_enabled=True,
        artifact_version="1",
    )
    frame = SimpleNamespace(data=b"\x01\x00" * 480, sample_rate=48000)
    await router.handle_frame("session-1", "teammate_1", frame)
    await router.publish_proxy_audio("session-1", b"\x02\x00" * 240)
    repository.add_transcript_segment(
        segment_id="proxy-segment-1",
        session_id="session-1",
        runtime_id="runtime-1",
        speaker="proxy",
        start_ms=10,
        end_ms=20,
        text="Proxy response",
        confidence=None,
        is_final=True,
        provider_version="mock-llm-v1",
    )

    await router.finalize("session-1", phase_version=5)

    assert published == [("session-1", b"\x02\x00" * 240)]
    assert (tmp_path / "session-1" / "runtime-1-teammate_1.wav").is_file()
    assert (tmp_path / "session-1" / "runtime-1-proxy.wav").is_file()
    artifacts = repository.list_session_artifacts("session-1")
    assert [artifact.kind for artifact in artifacts] == [
        "recording_manifest",
        "agent_log_manifest",
    ]
    recordings = json.loads(artifacts[0].content)
    assert {item["speaker"] for item in recordings} == {"teammate_1", "proxy"}
    agent_log = json.loads(artifacts[1].content)
    assert agent_log[0]["segment_id"] == "proxy-segment-1"
    artifact_messages = [
        row for row in repository.pending_outbox() if row.message_kind == "artifact"
    ]
    assert len(artifact_messages) == 2


@pytest.mark.asyncio
async def test_router_cancel_stops_session_before_proxy_disconnect(repository, tmp_path):
    pipeline = StubPipeline(repository)
    router = AudioPipelineRouter(pipeline, tmp_path, publish_audio=None)
    await router.start_session(
        "session-1",
        "runtime-1",
        {},
        proxy_enabled=True,
        artifact_version="1",
    )

    await router.cancel("session-1")

    assert pipeline.cancelled == ["session-1"]
    assert "session-1" not in router.sessions


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["task", "recorder", "pipeline", "manifest"])
async def test_finalize_failure_always_releases_router_and_pipeline_state(
    repository, tmp_path, monkeypatch, failure_point
):
    class FailingPipeline(StubPipeline):
        async def finalize(self, session_id, phase_version):
            if failure_point == "pipeline":
                raise RuntimeError("pipeline finalize failed")
            self.sessions.pop(session_id, None)

    pipeline = FailingPipeline(repository)
    router = AudioPipelineRouter(pipeline, tmp_path)
    await router.start_session(
        "session-1",
        "runtime-1",
        {},
        proxy_enabled=True,
        artifact_version="1",
    )

    if failure_point == "task":
        async def fail_task():
            raise RuntimeError("pending task failed")

        task = asyncio.create_task(fail_task())
        router.tasks["session-1"].add(task)
    elif failure_point == "recorder":
        monkeypatch.setattr(
            router,
            "_close_recorders",
            lambda *_args: (_ for _ in ()).throw(RuntimeError("recorder close failed")),
        )
    elif failure_point == "manifest":
        monkeypatch.setattr(
            router,
            "_create_manifests",
            lambda *_args: (_ for _ in ()).throw(RuntimeError("manifest failed")),
        )

    with pytest.raises(RuntimeError):
        await router.finalize("session-1", phase_version=5)

    assert "session-1" not in router.sessions
    assert "session-1" not in router.tasks
    assert all(key[0] != "session-1" for key in router.detectors)
    assert all(key[0] != "session-1" for key in router.recorders)
    assert "session-1" not in pipeline.sessions
    assert pipeline.cancelled == ["session-1"]

    await router.start_session(
        "session-1",
        "runtime-2",
        {},
        proxy_enabled=True,
        artifact_version="2",
    )
    assert router.sessions["session-1"].accepting_input is True
