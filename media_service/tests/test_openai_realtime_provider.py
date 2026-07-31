from __future__ import annotations

import pytest


class FakeRealtimeConnection:
    def __init__(self):
        self.frames = []
        self.committed = False

    async def send_frame(self, frame):
        self.frames.append(frame)

    async def commit(self):
        self.committed = True

    async def events(self):
        yield {"kind": "partial", "text": "hel", "start_ms": 0, "end_ms": 120}
        yield {"kind": "final", "text": "hello", "start_ms": 0, "end_ms": 240}


class FakeRealtimeTransport:
    def __init__(self):
        self.connection = FakeRealtimeConnection()
        self.calls = []

    async def connect_asr(self, *, model, api_key, utterance_id):
        self.calls.append((model, api_key, utterance_id))
        return self.connection


@pytest.mark.asyncio
async def test_openai_realtime_asr_uses_injected_transport():
    from media_service.app.audio_format import PcmFrame
    from media_service.app.providers.openai_realtime import OpenAIRealtimeAsrProvider

    transport = FakeRealtimeTransport()
    provider = OpenAIRealtimeAsrProvider("gpt-4o-transcribe", "test-key", transport=transport)
    session = await provider.open_asr_session(utterance_id="u1")

    await session.push(PcmFrame(b"pcm", 16000, 1, 1))
    await session.commit()
    events = [event async for event in session.events()]

    assert transport.calls == [("gpt-4o-transcribe", "test-key", "u1")]
    assert transport.connection.frames[0].data == b"pcm"
    assert transport.connection.committed is True
    assert [event.kind for event in events] == ["partial", "final"]
