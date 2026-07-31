from __future__ import annotations

import pytest


class FakeLlm:
    version = "fake-llm-v1"

    def __init__(self):
        self.calls = []

    async def complete(self, *, system_prompt, input_text):
        self.calls.append((system_prompt, input_text))
        return "Neutral response."


class FakeTts:
    version = "fake-tts-v1"

    async def synthesize(self, text):
        yield text.encode("utf-8")


@pytest.mark.asyncio
async def test_fixed_introduction_never_calls_llm(repository):
    from media_service.app.streaming_pipeline import AuditedStreamingProxyPipeline

    published = []
    fake_llm = FakeLlm()

    async def publish(session_id, chunk):
        published.append((session_id, chunk))

    pipeline = AuditedStreamingProxyPipeline(
        repository,
        llm=fake_llm,
        tts=FakeTts(),
        publish_audio=publish,
    )

    await pipeline.start_session("session-1", "runtime-1", {"materials": []})

    turns = repository.list_session_agent_turns("session-1")
    assert fake_llm.calls == []
    assert turns[0].turn_kind == "fixed_introduction"
    assert turns[0].status == "published"
    assert published
