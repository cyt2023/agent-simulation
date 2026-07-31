from __future__ import annotations

import pytest

from media_service.app.config import Settings


@pytest.mark.asyncio
async def test_asr_stream_emits_partial_before_final():
    from media_service.app.audio_format import PcmFrame
    from media_service.app.providers.mock import MockAsrProvider

    session = await MockAsrProvider().open_asr_session(utterance_id="u1")
    await session.push(PcmFrame(b"frame", 16000, 1, 1))
    await session.commit()
    events = [event async for event in session.events()]

    assert [event.kind for event in events] == ["partial", "final"]
    assert events[-1].utterance_id == "u1"


def test_formal_mode_rejects_batch_asr():
    from media_service.app.providers.factory import (
        ProviderCapabilityError,
        create_provider_bundle,
    )

    settings = Settings(
        media_database_url="sqlite+pysqlite:///:memory:",
        a_to_b_service_token="a-secret",
        study1_internal_api_key="b-secret",
        livekit_api_key="devkey",
        livekit_api_secret="test-livekit-secret-at-least-32-bytes",
        media_provider="openai",
        openai_api_key="test-key",
        openai_asr_model="whisper-1",
    )

    with pytest.raises(ProviderCapabilityError):
        create_provider_bundle(settings, formal=True)


def test_mock_bundle_declares_streaming_capabilities():
    from media_service.app.providers.factory import create_provider_bundle

    settings = Settings(
        media_database_url="sqlite+pysqlite:///:memory:",
        a_to_b_service_token="a-secret",
        study1_internal_api_key="b-secret",
        livekit_api_key="devkey",
        livekit_api_secret="test-livekit-secret-at-least-32-bytes",
        media_provider="mock",
    )

    bundle = create_provider_bundle(settings, formal=True)

    assert bundle.capabilities.streaming_asr is True
    assert bundle.capabilities.streaming_tts is True
