"""The complete and intentionally small A <-> B media boundary.

No ASR, LLM, TTS, RTC, microphone, recording, or live meeting implementation
lives here.  A issues command envelopes; B returns event/artifact envelopes.
"""

from __future__ import annotations

import copy
import threading
from typing import Any, Protocol


COMMANDS = {
    "START_PROXY_MEETING",
    "BEGIN_HANDOFF",
    "START_SYNC_MEETING",
    "STOP_SESSION",
}

EVENT_TYPES = {
    "MEDIA_READY",
    "PARTICIPANT_JOINED",
    "PARTICIPANT_LEFT",
    "HANDOFF_COMPLETE",
    "MEDIA_ERROR",
    "MEETING_ENDED",
}


class MediaGateway(Protocol):
    def send_command(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Send exactly one command envelope to B."""


class MockMediaGateway:
    """In-process contract double; it never creates live media."""

    def __init__(self):
        self._commands: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def send_command(self, envelope: dict[str, Any]) -> dict[str, Any]:
        command_id = str(envelope.get("command_id") or "")
        command = str(envelope.get("command") or "")
        if not command_id:
            raise ValueError("command_id is required")
        if command not in COMMANDS:
            raise ValueError(f"Unsupported media command: {command}")
        with self._lock:
            duplicate = command_id in self._commands
            if not duplicate:
                self._commands[command_id] = copy.deepcopy(envelope)
            return {
                "accepted": True,
                "duplicate": duplicate,
                "command_id": command_id,
                "mode": "mock",
            }

    @property
    def commands(self) -> list[dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(item) for item in self._commands.values()]
