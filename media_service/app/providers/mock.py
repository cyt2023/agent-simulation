from __future__ import annotations

from collections.abc import AsyncIterator
import json

from .base import AsrResult


class MockAsrProvider:
    version = "mock-asr-v1"

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
                return json.dumps({"items": []})
            first = segments[0]
            return json.dumps(
                {
                    "items": [
                        {
                            "text": first["text"],
                            "segment_ids": [first["segment_id"]],
                        }
                    ]
                }
            )
        return "Meeting statements were recorded with speaker attribution."


class MockTtsProvider:
    version = "mock-tts-v1"

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        yield b""
