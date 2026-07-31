from __future__ import annotations

from dataclasses import dataclass
import inspect


DEFAULT_PLAYBACK_SESSION = "__default__"


@dataclass(frozen=True)
class PlaybackGeneration:
    session_id: str
    turn_id: str
    generation_id: int


@dataclass
class _PlaybackState:
    generation: PlaybackGeneration
    interrupted: bool = False


class ProxyPlaybackController:
    """Generation-aware publisher for the server-side Proxy audio source.

    A barge-in interrupts exactly one active generation. Once interrupted, any
    late TTS frames carrying the old generation token are ignored, even if the
    upstream task cancellation arrives after the frame is produced.
    """

    def __init__(self, audio_source):
        self.audio_source = audio_source
        self._next_generation_id = 0
        self._active: dict[str, _PlaybackState] = {}

    def begin(
        self,
        turn_id: str,
        *,
        session_id: str = DEFAULT_PLAYBACK_SESSION,
    ) -> PlaybackGeneration:
        self._next_generation_id += 1
        generation = PlaybackGeneration(
            session_id=session_id,
            turn_id=turn_id,
            generation_id=self._next_generation_id,
        )
        self._active[session_id] = _PlaybackState(generation=generation)
        return generation

    async def interrupt(
        self,
        generation: PlaybackGeneration | None = None,
        *,
        session_id: str | None = None,
    ) -> bool:
        resolved_session_id = (
            generation.session_id
            if generation is not None
            else session_id or DEFAULT_PLAYBACK_SESSION
        )
        state = self._active.get(resolved_session_id)
        if not state:
            return False
        if generation is not None and state.generation != generation:
            return False
        if state.interrupted:
            return False
        state.interrupted = True
        clear_queue = getattr(self.audio_source, "clear_queue", None)
        if clear_queue:
            await _maybe_await(clear_queue())
        return True

    async def publish(self, generation: PlaybackGeneration, frame) -> bool:
        state = self._active.get(generation.session_id)
        if not state or state.generation != generation or state.interrupted:
            return False
        await _maybe_await(self.audio_source.capture_frame(frame))
        return True

    def is_active(self, generation: PlaybackGeneration) -> bool:
        state = self._active.get(generation.session_id)
        return bool(state and state.generation == generation and not state.interrupted)


async def _maybe_await(result):
    if inspect.isawaitable(result):
        return await result
    return result
