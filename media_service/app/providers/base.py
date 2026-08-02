from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from ..audio_format import PcmFrame


@dataclass(frozen=True)
class AsrResult:
    text: str
    start_ms: int
    end_ms: int
    confidence: float | None
    is_final: bool


@dataclass(frozen=True)
class AsrEvent:
    utterance_id: str
    kind: str
    text: str
    start_ms: int
    end_ms: int
    confidence: float | None
    provider_version: str


@dataclass(frozen=True)
class LlmDelta:
    text: str
    index: int
    is_final: bool = False


@dataclass(frozen=True)
class TtsFrame:
    data: bytes
    sample_rate_hz: int
    channels: int
    sequence_no: int


@dataclass(frozen=True)
class ProviderCapabilities:
    streaming_asr: bool
    streaming_llm: bool
    streaming_tts: bool
    batch_asr: bool = False


class StreamingAsrSession(Protocol):
    async def push(self, frame: PcmFrame) -> None: ...

    async def commit(self) -> None: ...

    async def events(self) -> AsyncIterator[AsrEvent]: ...


class StreamingAsrProvider(Protocol):
    version: str

    async def transcribe(
        self, audio: AsyncIterator[bytes], *, speaker: str
    ) -> AsyncIterator[AsrResult]: ...

    async def open_asr_session(self, *, utterance_id: str) -> StreamingAsrSession: ...


class LanguageModelProvider(Protocol):
    version: str

    async def complete(self, *, system_prompt: str, input_text: str) -> str: ...


class StreamingTtsProvider(Protocol):
    version: str

    async def synthesize(self, text: str) -> AsyncIterator[bytes]: ...
