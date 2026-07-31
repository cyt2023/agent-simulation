"""The complete and intentionally small A <-> B media boundary.

No ASR, LLM, TTS, RTC, microphone, recording, or live meeting implementation
lives here.  A issues command envelopes; B returns event/artifact envelopes.
"""

from __future__ import annotations

import copy
import os
import threading
from typing import Any, Protocol

import requests


COMMANDS = {
    "START_PROXY_MEETING",
    "END_CURRENT_MEETING",
    "BEGIN_HANDOFF",
    "START_SYNC_MEETING",
    "REGENERATE_SUMMARY",
    "STOP_SESSION",
    "PURGE_SESSION_MEDIA",
}

EVENT_TYPES = {
    "MEDIA_READY",
    "PARTICIPANT_JOINED",
    "PARTICIPANT_LEFT",
    "HANDOFF_COMPLETE",
    "MEDIA_ERROR",
    "MEETING_ENDED",
    "MEDIA_PURGED",
    "MEDIA_CONFIG_FROZEN",
    "AGENT_TURN_STARTED",
    "AGENT_TURN_COMPLETED",
    "AGENT_TURN_FAILED",
    "RTC_METRIC_BATCH",
    "COMPONENT_HEALTH",
    "RECORDING_TRACK_FINALIZED",
}


class MediaGateway(Protocol):
    mode: str

    def send_command(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Send exactly one command envelope to B."""

    def issue_access(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    def get_status(self, session_id: str) -> dict[str, Any]: ...

    def export_bundle(self, session_id: str) -> bytes | None: ...

    def get_recording(
        self, session_id: str, recording_id: str, range_header: str | None = None
    ): ...

    def report_device(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class MediaGatewayError(RuntimeError):
    """A controlled B-service transport or response failure."""


class HttpMediaGateway:
    mode = "http"

    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        timeout_seconds: float = 10.0,
        session=None,
    ):
        if not base_url or not service_token:
            raise ValueError("MEDIA_SERVICE_URL and A_TO_B_SERVICE_TOKEN are required")
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def _request(self, method: str, path: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self.service_token}"
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                timeout=self.timeout_seconds,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            raise MediaGatewayError(f"Study 1 media service request failed: {error}") from error

    def send_command(self, envelope: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/internal/commands", json=envelope).json()

    def issue_access(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/internal/media-access", json=payload).json()

    def get_status(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/internal/sessions/{session_id}/status").json()

    def report_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/internal/device-status", json=payload).json()

    def export_bundle(self, session_id: str) -> bytes:
        return self._request("GET", f"/internal/sessions/{session_id}/export").content

    def get_recording(
        self, session_id: str, recording_id: str, range_header: str | None = None
    ):
        headers = {"Range": range_header} if range_header else {}
        return self._request(
            "GET",
            f"/internal/sessions/{session_id}/recordings/{recording_id}",
            headers=headers,
        )


class MockMediaGateway:
    """In-process contract double; it never creates live media."""

    def __init__(self):
        self.mode = "mock"
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

    def issue_access(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "available": False,
            "mode": "mock",
            "session_id": payload["session_id"],
            "phase": payload["phase"],
        }

    def get_status(self, session_id: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "service_status": "mock",
            "runtime_state": "IDLE",
            "mode": "mock",
            "components": {
                "recorder": {"status": "unknown"},
                "asr": {"status": "unknown"},
                "llm": {"status": "unknown"},
                "tts": {"status": "unknown"},
                "proxy": {"status": "unknown"},
            },
        }

    def export_bundle(self, session_id: str) -> None:
        return None

    def get_recording(
        self, session_id: str, recording_id: str, range_header: str | None = None
    ):
        raise MediaGatewayError("Recording replay is unavailable in Mock media mode")

    def report_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "accepted": True,
            "mode": "mock",
            "session_id": payload["session_id"],
        }

    @property
    def commands(self) -> list[dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(item) for item in self._commands.values()]


def create_media_gateway_from_env() -> MediaGateway:
    mode = os.environ.get("MEDIA_GATEWAY_MODE", "mock").strip().lower()
    if mode == "mock":
        return MockMediaGateway()
    if mode != "http":
        raise ValueError(f"Unsupported MEDIA_GATEWAY_MODE: {mode}")
    return HttpMediaGateway(
        os.environ.get("MEDIA_SERVICE_URL", "http://media-service:8000"),
        os.environ.get("A_TO_B_SERVICE_TOKEN", ""),
        timeout_seconds=float(os.environ.get("MEDIA_SERVICE_TIMEOUT_SECONDS", "10")),
    )
