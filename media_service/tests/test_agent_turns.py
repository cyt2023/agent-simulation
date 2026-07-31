from __future__ import annotations

import pytest


class FailingLlm:
    version = "failing-llm-v1"

    async def complete(self, *, system_prompt, input_text):
        raise TimeoutError("provider timeout")


class RecordingTts:
    version = "recording-tts-v1"

    def __init__(self):
        self.requests = []

    async def synthesize(self, text):
        self.requests.append(text)
        yield b"audio"


@pytest.mark.asyncio
async def test_llm_exhaustion_records_error_and_no_audio(repository):
    from media_service.app.proxy_state import ProxyState
    from media_service.app.streaming_pipeline import AuditedStreamingProxyPipeline

    published = []
    tts = RecordingTts()

    async def publish(session_id, chunk):
        published.append((session_id, chunk))

    pipeline = AuditedStreamingProxyPipeline(
        repository,
        llm=FailingLlm(),
        tts=tts,
        publish_audio=publish,
        max_llm_attempts=1,
    )
    await pipeline.start_session("session-1", "runtime-1", {"materials": []})
    published.clear()
    tts.requests.clear()

    await pipeline.process_final_utterance(
        {
            "utterance_id": "u1",
            "session_id": "session-1",
            "speaker": "teammate_1",
            "text": "We should compare the costs.",
        }
    )

    turn = repository.list_session_agent_turns("session-1")[-1]
    assert turn.error_code == "LLM_TIMEOUT"
    assert turn.status == "failed"
    assert published == []
    assert tts.requests == []
    assert pipeline.proxy_state("session-1") == ProxyState.TECHNICAL_ISSUE
