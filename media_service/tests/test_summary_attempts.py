import json

import pytest

from media_service.app.transcript import TranscriptSegment


class FlakySummaryLlm:
    version = "fake-llm-v1"

    def __init__(self):
        self.calls = 0

    async def complete(self, *, system_prompt, input_text):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("provider timeout")
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


def segments():
    return [
        TranscriptSegment(
            segment_id="seg-1",
            session_id="session-1",
            runtime_id="runtime-1",
            speaker="teammate_1",
            start_ms=0,
            end_ms=1000,
            text="The north route has lower cost.",
            confidence=0.9,
            is_final=True,
            provider_version="fake-asr-v1",
        )
    ]


@pytest.mark.asyncio
async def test_failed_first_summary_attempt_can_retry_same_config(repository):
    from media_service.app.summary_attempts import SummaryAttemptService

    service = SummaryAttemptService(
        repository,
        FlakySummaryLlm(),
        prompt_version="neutral-summary-v1",
        sampling={"temperature": 0},
    )

    failed = await service.generate("session-1", segments())
    retried = await service.retry_same_config(
        "session-1",
        failed.attempt_id,
        reason="Provider recovered",
    )

    assert failed.status == "failed"
    assert retried.status == "succeeded"
    assert retried.parent_attempt_id == failed.attempt_id
    assert retried.config_checksum == failed.config_checksum
    assert len(repository.list_session_summary_attempts("session-1")) == 2


@pytest.mark.asyncio
async def test_retry_rejects_configuration_drift(repository):
    from media_service.app.summary_attempts import SummaryAttemptService, SummaryPolicyError

    service = SummaryAttemptService(
        repository,
        FlakySummaryLlm(),
        prompt_version="neutral-summary-v1",
        sampling={"temperature": 0},
    )
    failed = await service.generate("session-1", segments())

    with pytest.raises(SummaryPolicyError, match="frozen"):
        await service.retry_same_config(
            "session-1",
            failed.attempt_id,
            reason="retry",
            expected_config_checksum="changed",
        )
