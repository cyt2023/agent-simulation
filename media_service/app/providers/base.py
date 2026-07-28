from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AsrResult:
    text: str
    start_ms: int
    end_ms: int
    confidence: float | None
    is_final: bool


class StreamingAsrProvider(Protocol):
    version: str

    async def transcribe(
        self, audio: AsyncIterator[bytes], *, speaker: str
    ) -> AsyncIterator[AsrResult]: ...


class LanguageModelProvider(Protocol):
    version: str

    async def complete(self, *, system_prompt: str, input_text: str) -> str: ...


class StreamingTtsProvider(Protocol):
    version: str

    async def synthesize(self, text: str) -> AsyncIterator[bytes]: ...
