from __future__ import annotations

from typing import Any, Protocol

from ..audio_format import PcmFrame
from .base import AsrEvent


class RealtimeAsrConnection(Protocol):
    async def send_frame(self, frame: PcmFrame) -> None: ...

    async def commit(self) -> None: ...

    async def events(self): ...


class RealtimeAsrTransport(Protocol):
    async def connect_asr(
        self, *, model: str, api_key: str, utterance_id: str
    ) -> RealtimeAsrConnection: ...


class MissingRealtimeTransport:
    async def connect_asr(self, *, model: str, api_key: str, utterance_id: str):
        raise RuntimeError("OpenAI realtime ASR requires an injected transport")


class OpenAIRealtimeAsrProvider:
    def __init__(
        self,
        model: str,
        api_key: str,
        *,
        transport: RealtimeAsrTransport | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.version = f"openai-realtime:{model}"
        self.transport = transport or MissingRealtimeTransport()

    async def open_asr_session(self, *, utterance_id: str):
        connection = await self.transport.connect_asr(
            model=self.model,
            api_key=self.api_key,
            utterance_id=utterance_id,
        )
        return OpenAIRealtimeAsrSession(utterance_id, connection, self.version)


class OpenAIRealtimeAsrSession:
    def __init__(
        self,
        utterance_id: str,
        connection: RealtimeAsrConnection,
        provider_version: str,
    ):
        self.utterance_id = utterance_id
        self.connection = connection
        self.provider_version = provider_version

    async def push(self, frame: PcmFrame) -> None:
        await self.connection.send_frame(frame)

    async def commit(self) -> None:
        await self.connection.commit()

    async def events(self):
        async for event in self.connection.events():
            yield _asr_event(self.utterance_id, self.provider_version, event)


def _asr_event(
    utterance_id: str, provider_version: str, event: MappingOrObject
) -> AsrEvent:
    if isinstance(event, AsrEvent):
        return event
    if isinstance(event, dict):
        value = event
        getter = value.get
    else:
        getter = lambda name, default=None: getattr(event, name, default)
    return AsrEvent(
        utterance_id=utterance_id,
        kind=str(getter("kind", "partial")),
        text=str(getter("text", "")),
        start_ms=int(getter("start_ms", 0) or 0),
        end_ms=int(getter("end_ms", 0) or 0),
        confidence=getter("confidence", None),
        provider_version=provider_version,
    )


MappingOrObject = dict[str, Any] | Any
