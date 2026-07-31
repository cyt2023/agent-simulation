from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Protocol

from .models import MediaSummaryAttemptRow
from .repository import MediaRepository
from .summary import NEUTRAL_SUMMARY_PROMPT, SummaryService
from .transcript import TranscriptSegment


class SummaryPolicyError(RuntimeError):
    pass


class LanguageModel(Protocol):
    version: str

    async def complete(self, *, system_prompt: str, input_text: str) -> str: ...


def _json_checksum(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _segments_payload(segments: list[TranscriptSegment]) -> list[dict[str, Any]]:
    return [
        {
            "segment_id": segment.segment_id,
            "session_id": segment.session_id,
            "runtime_id": segment.runtime_id,
            "speaker": segment.speaker,
            "start_ms": segment.start_ms,
            "end_ms": segment.end_ms,
            "text": segment.text,
            "confidence": segment.confidence,
            "is_final": segment.is_final,
            "provider_version": segment.provider_version,
        }
        for segment in segments
        if segment.is_final
    ]


def _segments_from_input(input_text: str) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            segment_id=str(item["segment_id"]),
            session_id=str(item.get("session_id") or ""),
            runtime_id=str(item.get("runtime_id") or ""),
            speaker=str(item["speaker"]),
            start_ms=int(item["start_ms"]),
            end_ms=int(item["end_ms"]),
            text=str(item["text"]),
            confidence=item.get("confidence"),
            is_final=bool(item.get("is_final", True)),
            provider_version=str(item.get("provider_version") or ""),
        )
        for item in json.loads(input_text)
    ]


class SummaryAttemptService:
    def __init__(
        self,
        repository: MediaRepository,
        llm: LanguageModel,
        *,
        prompt_version: str,
        sampling: dict[str, Any] | None = None,
    ):
        self.repository = repository
        self.llm = llm
        self.prompt_version = prompt_version
        self.sampling = dict(sampling or {"temperature": 0})

    async def generate(
        self,
        session_id: str,
        segments: list[TranscriptSegment],
        *,
        reason: str | None = None,
        parent_attempt_id: str | None = None,
    ) -> MediaSummaryAttemptRow:
        payload = _segments_payload(segments)
        input_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        transcript_checksum = hashlib.sha256(input_text.encode("utf-8")).hexdigest()
        config = self._frozen_config(transcript_checksum)
        return await self._run_attempt(
            session_id,
            input_text=input_text,
            transcript_checksum=transcript_checksum,
            config=config,
            reason=reason,
            parent_attempt_id=parent_attempt_id,
        )

    async def retry_same_config(
        self,
        session_id: str,
        parent_attempt_id: str,
        *,
        reason: str,
        expected_config_checksum: str | None = None,
    ) -> MediaSummaryAttemptRow:
        parent = self.repository.get_summary_attempt(parent_attempt_id)
        if parent.session_id != session_id:
            raise SummaryPolicyError("Parent attempt belongs to another session")
        if expected_config_checksum and expected_config_checksum != parent.config_checksum:
            raise SummaryPolicyError("Summary retry must use the frozen configuration")
        config = {
            "prompt_version": parent.prompt_version,
            "provider_version": parent.provider_version,
            "sampling": parent.sampling,
            "transcript_checksum": parent.transcript_checksum,
        }
        if _json_checksum(config) != parent.config_checksum:
            raise SummaryPolicyError("Stored parent attempt has a non-frozen configuration")
        return await self._run_attempt(
            session_id,
            input_text=parent.input_text,
            transcript_checksum=parent.transcript_checksum,
            config=config,
            reason=reason,
            parent_attempt_id=parent_attempt_id,
        )

    def _frozen_config(self, transcript_checksum: str) -> dict[str, Any]:
        return {
            "prompt_version": self.prompt_version,
            "provider_version": getattr(self.llm, "version", "unknown"),
            "sampling": self.sampling,
            "transcript_checksum": transcript_checksum,
        }

    async def _run_attempt(
        self,
        session_id: str,
        *,
        input_text: str,
        transcript_checksum: str,
        config: dict[str, Any],
        reason: str | None,
        parent_attempt_id: str | None,
    ) -> MediaSummaryAttemptRow:
        attempt = self.repository.begin_summary_attempt(
            attempt_id=str(uuid.uuid4()),
            session_id=session_id,
            parent_attempt_id=parent_attempt_id,
            prompt_version=str(config["prompt_version"]),
            prompt_sha256=hashlib.sha256(
                NEUTRAL_SUMMARY_PROMPT.encode("utf-8")
            ).hexdigest(),
            transcript_checksum=transcript_checksum,
            config_checksum=_json_checksum(config),
            provider_version=str(config["provider_version"]),
            sampling=dict(config["sampling"]),
            input_text=input_text,
            reason=reason,
        )
        try:
            raw = (
                await self.llm.complete(
                    system_prompt=NEUTRAL_SUMMARY_PROMPT,
                    input_text=input_text,
                )
            ).strip()
            content = SummaryService._validate_and_render(
                raw, _segments_from_input(input_text)
            )
        except Exception as error:
            return self.repository.finish_summary_attempt(
                attempt.attempt_id,
                status="failed",
                error_code=type(error).__name__,
                error_message=str(error),
            )
        return self.repository.finish_summary_attempt(
            attempt.attempt_id,
            status="succeeded",
            output_text=content,
        )
