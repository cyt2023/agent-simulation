from __future__ import annotations

from collections.abc import AsyncIterator
import io
import json
import zipfile

import pytest

from media_service.app.pipeline import PROXY_PROMPT, ProxyMediaPipeline
from media_service.app.providers.base import AsrResult


class FakeAsr:
    version = "fake-asr-v1"

    async def transcribe(self, audio: AsyncIterator[bytes], *, speaker: str):
        payload = b""
        async for chunk in audio:
            payload += chunk
        assert payload == b"human-pcm"
        yield AsrResult(
            text="The north route has lower cost.",
            start_ms=100,
            end_ms=900,
            confidence=0.93,
            is_final=True,
        )


class FakeLlm:
    version = "fake-llm-v1"

    def __init__(self):
        self.calls = []

    async def complete(self, *, system_prompt, input_text):
        self.calls.append((system_prompt, input_text))
        if "factual meeting record" in system_prompt:
            transcript = json.loads(input_text)
            return json.dumps(
                {
                    "items": [
                        {
                            "text": "The north route has lower cost.",
                            "segment_ids": [transcript[0]["segment_id"]],
                        }
                    ]
                }
            )
        return "I heard that the north route has lower cost."


class FakeTts:
    version = "fake-tts-v1"

    async def synthesize(self, text):
        assert text == "I heard that the north route has lower cost."
        yield b"proxy-pcm-1"
        yield b"proxy-pcm-2"


def test_proxy_prompt_explicitly_limits_live_participation_to_neutral_relay():
    prompt = PROXY_PROMPT.casefold()

    for required in (
        "do not recommend",
        "do not rank",
        "do not persuade",
        "do not pressure",
        "do not present any option as best",
        "attribute p-authorized",
    ):
        assert required in prompt


@pytest.mark.asyncio
async def test_proxy_pipeline_transcribes_replies_and_persists_artifacts(repository, tmp_path):
    published = []
    llm = FakeLlm()

    async def publish(session_id, chunk):
        published.append((session_id, chunk))

    pipeline = ProxyMediaPipeline(
        repository,
        FakeAsr(),
        llm,
        FakeTts(),
        publish_audio=publish,
        media_root=tmp_path,
        proxy_prompt_version="proxy-v1",
        summary_prompt_version="neutral-summary-v1",
    )
    pipeline.start_session(
        "session-1",
        "runtime-1",
        {"materials": [{"title": "P evidence", "content": "Authorized fact"}]},
    )

    await pipeline.process_utterance(
        "session-1", "teammate_1", b"human-pcm", start_ms=100, end_ms=900
    )
    await pipeline.finalize("session-1", phase_version=5)

    assert published == [
        ("session-1", b"proxy-pcm-1"),
        ("session-1", b"proxy-pcm-2"),
    ]
    segments = repository.list_session_segments("session-1")
    assert [(item.speaker, item.text) for item in segments] == [
        ("teammate_1", "The north route has lower cost."),
        ("proxy", "I heard that the north route has lower cost."),
    ]
    assert "Authorized fact" in llm.calls[0][1]
    artifacts = repository.list_session_artifacts("session-1")
    assert [item.kind for item in artifacts] == ["transcript", "summary"]
    assert all(item.generator_version for item in artifacts)
    artifact_messages = [
        row for row in repository.pending_outbox() if row.message_kind == "artifact"
    ]
    assert len(artifact_messages) == 2

    await pipeline.regenerate_summary(
        "session-1",
        phase_version=8,
        reason="ASR correction approved by researcher",
        source_transcript_checksum=artifacts[0].checksum,
        source_summary_version="1",
    )
    summaries = [
        item for item in repository.list_session_artifacts("session-1")
        if item.kind == "summary"
    ]
    assert [item.version for item in summaries] == ["1", "2"]
    assert summaries[-1].metadata_json["regeneration_reason"] == (
        "ASR correction approved by researcher"
    )


@pytest.mark.asyncio
async def test_asr_relative_timestamps_are_offset_by_utterance_start(repository, tmp_path):
    async def publish(_session_id, _chunk):
        pass

    pipeline = ProxyMediaPipeline(
        repository,
        FakeAsr(),
        FakeLlm(),
        FakeTts(),
        publish_audio=publish,
        media_root=tmp_path,
        proxy_prompt_version="proxy-v1",
        summary_prompt_version="neutral-summary-v1",
    )
    pipeline.start_session(
        "session-1", "runtime-1", {}, proxy_enabled=False, artifact_version="sync-7"
    )

    await pipeline.process_utterance(
        "session-1", "teammate_1", b"human-pcm", start_ms=5000, end_ms=6000
    )

    segment = repository.list_session_segments("session-1")[0]
    assert (segment.start_ms, segment.end_ms) == (5100, 5900)


class AdvocacyLlm:
    version = "advocacy-llm-v1"

    async def complete(self, *, system_prompt, input_text):
        return "The team should use the north route."


class RecordingTts:
    version = "recording-tts-v1"

    def __init__(self):
        self.requests = []

    async def synthesize(self, text):
        self.requests.append(text)
        yield b"should-not-publish"


@pytest.mark.asyncio
async def test_proxy_pipeline_blocks_non_neutral_live_response(repository, tmp_path):
    published = []
    tts = RecordingTts()

    async def publish(session_id, chunk):
        published.append((session_id, chunk))

    pipeline = ProxyMediaPipeline(
        repository,
        FakeAsr(),
        AdvocacyLlm(),
        tts,
        publish_audio=publish,
        media_root=tmp_path,
        proxy_prompt_version="proxy-v1",
        summary_prompt_version="neutral-summary-v1",
    )
    pipeline.start_session("session-1", "runtime-1", {"materials": []})

    await pipeline.process_utterance(
        "session-1", "teammate_1", b"human-pcm", start_ms=100, end_ms=900
    )

    assert published == []
    assert tts.requests == []
    assert [(row.speaker, row.text) for row in repository.list_session_segments("session-1")] == [
        ("teammate_1", "The north route has lower cost."),
    ]
    event = repository.pending_outbox()[-1]
    assert event.event_type == "MEDIA_PROXY_NEUTRALITY_BLOCKED"
    assert event.payload["runtime_id"] == "runtime-1"
