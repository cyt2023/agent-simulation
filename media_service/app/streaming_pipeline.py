from __future__ import annotations

import inspect
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from .agent_turns import AgentTurnLedger
from .announcements import (
    FIXED_PROXY_INTRODUCTION,
    FIXED_PROXY_INTRODUCTION_VERSION,
)
from .context_builder import build_authorized_context_snapshot
from .errors import MediaComponentError
from .provider_execution import execute_with_retries
from .providers.base import LanguageModelProvider, StreamingTtsProvider
from .proxy_state import ProxyState
from .repository import MediaRepository


class AuditedStreamingProxyPipeline:
    def __init__(
        self,
        repository: MediaRepository,
        *,
        llm: LanguageModelProvider,
        tts: StreamingTtsProvider,
        publish_audio: Callable[[str, bytes], Awaitable[None]],
        max_llm_attempts: int = 2,
        llm_timeout_seconds: float = 10.0,
    ):
        self.repository = repository
        self.llm = llm
        self.tts = tts
        self.publish_audio = publish_audio
        self.max_llm_attempts = max_llm_attempts
        self.llm_timeout_seconds = llm_timeout_seconds
        self.ledger = AgentTurnLedger(repository)
        self._sessions: dict[str, dict] = {}
        self._states: dict[str, ProxyState] = {}
        self.begin_proxy_playback: Callable[[str, str], Any] | None = None

    async def start_session(
        self, session_id: str, runtime_id: str, authorized_context: dict
    ) -> None:
        self._sessions[session_id] = {
            "runtime_id": runtime_id,
            "authorized_context": dict(authorized_context),
            "phase_version": 1,
        }
        self._states[session_id] = ProxyState.SPEAKING
        snapshot = build_authorized_context_snapshot(
            authorized_context,
            context_event_ids=["session_started"],
        )
        turn = self.ledger.begin(
            turn_id=str(uuid.uuid4()),
            session_id=session_id,
            runtime_id=runtime_id,
            phase_version=1,
            turn_kind="fixed_introduction",
            context_event_ids=["session_started"],
            authorized_snapshot={
                **snapshot,
                "announcement_version": FIXED_PROXY_INTRODUCTION_VERSION,
            },
        )
        generation = (
            self.begin_proxy_playback(session_id, turn.turn_id)
            if self.begin_proxy_playback
            else None
        )
        async for chunk in self.tts.synthesize(FIXED_PROXY_INTRODUCTION):
            if chunk:
                await _publish_audio_chunk(
                    self.publish_audio,
                    session_id,
                    chunk,
                    generation=generation,
                )
        self.repository.finish_agent_turn(turn.turn_id, status="published")
        self._states[session_id] = ProxyState.LISTENING

    async def process_final_utterance(self, utterance: dict) -> None:
        session_id = str(utterance["session_id"])
        session = self._sessions[session_id]
        runtime_id = session["runtime_id"]
        context_event_ids = [str(utterance["utterance_id"])]
        snapshot = build_authorized_context_snapshot(
            session["authorized_context"],
            context_event_ids=context_event_ids,
            current_utterance=utterance,
        )
        turn = self.ledger.begin(
            turn_id=str(uuid.uuid4()),
            session_id=session_id,
            runtime_id=runtime_id,
            phase_version=session["phase_version"],
            turn_kind="llm_response",
            context_event_ids=context_event_ids,
            authorized_snapshot=snapshot,
        )
        self._states[session_id] = ProxyState.THINKING
        try:
            response_text = await execute_with_retries(
                "llm",
                lambda: self.llm.complete(
                    system_prompt="Study 1 neutral proxy response",
                    input_text=snapshot["input_text"],
                ),
                attempts=self.max_llm_attempts,
                timeout_seconds=self.llm_timeout_seconds,
            )
        except MediaComponentError as error:
            self.repository.finish_agent_turn(
                turn.turn_id,
                status="failed",
                error_code=error.code,
            )
            self._states[session_id] = ProxyState.TECHNICAL_ISSUE
            self.repository.enqueue_event(
                session_id,
                session["phase_version"],
                "MEDIA_ERROR",
                {"error_code": error.code, "turn_id": turn.turn_id},
            )
            return
        if not response_text.strip():
            self.repository.finish_agent_turn(
                turn.turn_id,
                status="failed",
                error_code="LLM_EMPTY_RESPONSE",
            )
            self._states[session_id] = ProxyState.TECHNICAL_ISSUE
            return
        self._states[session_id] = ProxyState.SPEAKING
        generation = (
            self.begin_proxy_playback(session_id, turn.turn_id)
            if self.begin_proxy_playback
            else None
        )
        async for chunk in self.tts.synthesize(response_text):
            if chunk:
                await _publish_audio_chunk(
                    self.publish_audio,
                    session_id,
                    chunk,
                    generation=generation,
                )
        self.repository.finish_agent_turn(turn.turn_id, status="published")
        self._states[session_id] = ProxyState.LISTENING

    def proxy_state(self, session_id: str) -> ProxyState:
        return self._states.get(session_id, ProxyState.LISTENING)


async def _publish_audio_chunk(
    callback,
    session_id: str,
    chunk: bytes,
    *,
    generation,
) -> None:
    if generation is not None and _accepts_keyword(callback, "generation"):
        await callback(session_id, chunk, generation=generation)
        return
    await callback(session_id, chunk)


def _accepts_keyword(callback, keyword: str) -> bool:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        or parameter.name == keyword
        for parameter in signature.parameters.values()
    )
