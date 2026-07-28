from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from media_service.app.audio_router import AudioPipelineRouter


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

    async def regenerate_summary(self, *args, **kwargs):
        pass


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
