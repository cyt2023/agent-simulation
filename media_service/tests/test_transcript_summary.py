from __future__ import annotations

import json
import pytest

from media_service.app.summary import NeutralityError, SummaryService
from media_service.app.transcript import TranscriptBuilder, TranscriptSegment


def test_transcript_preserves_auditable_timestamps_and_speaker():
    builder = TranscriptBuilder("session-1", "runtime-1", "mock-asr-v1")
    segment = builder.add_final(
        speaker="teammate_1",
        start_ms=1250,
        end_ms=2730,
        text="The north route is shorter.",
        confidence=0.91,
    )

    assert segment.speaker == "teammate_1"
    assert segment.start_ms == 1250
    assert segment.end_ms == 2730
    assert segment.is_final is True
    assert segment.provider_version == "mock-asr-v1"
    assert builder.checksum()


class FakeLlm:
    def __init__(self, output):
        self.output = output
        self.calls = []

    async def complete(self, *, system_prompt, input_text):
        self.calls.append((system_prompt, input_text))
        return self.output


@pytest.mark.asyncio
async def test_summary_uses_transcript_without_delegation_measurements():
    llm = FakeLlm(
        json.dumps(
            {
                "items": [
                    {
                        "text": "The north route is shorter.",
                        "segment_ids": ["seg-1"],
                    }
                ]
            }
        )
    )
    service = SummaryService(llm, prompt_version="neutral-summary-v1")
    segments = [
        TranscriptSegment(
            segment_id="seg-1",
            session_id="session-1",
            runtime_id="runtime-1",
            speaker="teammate_1",
            start_ms=0,
            end_ms=1000,
            text="The north route is shorter.",
            confidence=0.9,
            is_final=True,
            provider_version="mock-asr-v1",
        )
    ]

    result = await service.generate(segments)

    assert result.prompt_version == "neutral-summary-v1"
    assert "north route" in result.content
    assert "[segment:seg-1]" in result.content
    assert "delegation" not in llm.calls[0][1].lower()


@pytest.mark.asyncio
async def test_summary_rejects_recommendations():
    llm = FakeLlm(
        json.dumps(
            {
                "items": [
                    {
                        "text": "The north route is preferable.",
                        "segment_ids": ["seg-1"],
                    }
                ]
            }
        )
    )
    service = SummaryService(
        llm,
        prompt_version="neutral-summary-v1",
    )
    with pytest.raises(NeutralityError):
        await service.generate(
            [
                TranscriptSegment(
                    segment_id="seg-1",
                    session_id="session-1",
                    runtime_id="runtime-1",
                    speaker="teammate_1",
                    start_ms=0,
                    end_ms=1000,
                    text="The north route is shorter.",
                    confidence=0.9,
                    is_final=True,
                    provider_version="mock-asr-v1",
                )
            ]
        )
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_summary_rejects_unknown_segments_and_outside_facts_after_one_retry():
    llm = FakeLlm(
        json.dumps(
            {
                "items": [
                    {
                        "text": "The south route has lower cost.",
                        "segment_ids": ["missing-segment"],
                    }
                ]
            }
        )
    )
    service = SummaryService(llm, prompt_version="neutral-summary-v1")
    segment = TranscriptSegment(
        segment_id="seg-1",
        session_id="session-1",
        runtime_id="runtime-1",
        speaker="teammate_1",
        start_ms=0,
        end_ms=1000,
        text="The north route is shorter.",
        confidence=0.9,
        is_final=True,
        provider_version="mock-asr-v1",
    )

    with pytest.raises(NeutralityError, match="segment"):
        await service.generate([segment])

    assert len(llm.calls) == 2
    assert llm.calls[0] == llm.calls[1]
