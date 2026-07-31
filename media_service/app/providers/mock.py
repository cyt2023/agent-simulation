from __future__ import annotations

from collections.abc import AsyncIterator
import json

from ..audio_format import PcmFrame
from .base import AsrEvent, AsrResult


class MockAsrSession:
    def __init__(self, utterance_id: str, provider_version: str):
        self.utterance_id = utterance_id
        self.provider_version = provider_version
        self.frames: list[PcmFrame] = []
        self._committed = False

    async def push(self, frame: PcmFrame) -> None:
        self.frames.append(frame)

    async def commit(self) -> None:
        self._committed = True

    async def events(self):
        if not self._committed:
            return
        total = sum(len(frame.data) for frame in self.frames)
        text = f"[streamed audio {total} bytes]"
        yield AsrEvent(
            utterance_id=self.utterance_id,
            kind="partial",
            text=text,
            start_ms=0,
            end_ms=max(20, total // 96),
            confidence=None,
            provider_version=self.provider_version,
        )
        yield AsrEvent(
            utterance_id=self.utterance_id,
            kind="final",
            text=text,
            start_ms=0,
            end_ms=max(20, total // 96),
            confidence=1.0,
            provider_version=self.provider_version,
        )


class MockAsrProvider:
    version = "mock-asr-v1"

    async def open_asr_session(self, *, utterance_id: str) -> MockAsrSession:
        return MockAsrSession(utterance_id, self.version)

    async def transcribe(
        self, audio: AsyncIterator[bytes], *, speaker: str
    ) -> AsyncIterator[AsrResult]:
        elapsed = 0
        async for chunk in audio:
            duration = max(20, len(chunk) // 96)
            yield AsrResult(
                text=f"[{speaker} audio {len(chunk)} bytes]",
                start_ms=elapsed,
                end_ms=elapsed + duration,
                confidence=1.0,
                is_final=True,
            )
            elapsed += duration


class MockLanguageModelProvider:
    version = "mock-llm-v1"

    async def complete(self, *, system_prompt: str, input_text: str) -> str:
        if "factual meeting record" in system_prompt:
            segments = json.loads(input_text)
            if not segments:
                return json.dumps({"sections": {}})
            first = segments[0]
            return json.dumps(
                {
                    "sections": {
                        "discussion_overview": [
                            {
                                "text": first["text"],
                                "segment_ids": [first["segment_id"]],
                            }
                        ]
                    }
                }
            )
        return "Meeting statements were recorded with speaker attribution."


class MockTtsProvider:
    version = "mock-tts-v1"

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        yield b""
