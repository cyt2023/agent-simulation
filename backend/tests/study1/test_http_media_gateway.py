from __future__ import annotations

import io

import pytest
import requests

from study1.media_gateway import HttpMediaGateway, MediaGatewayError


class FakeResponse:
    def __init__(self, payload=None, *, content=b"", status_code=200):
        self._payload = payload or {}
        self.content = content
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []
        self.response = FakeResponse(
            {"accepted": True, "duplicate": False, "command_id": "command-1"}
        )

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def test_http_gateway_sends_service_bearer_and_timeout():
    transport = FakeSession()
    gateway = HttpMediaGateway(
        "http://media-service:8000", "service-secret", timeout_seconds=4, session=transport
    )

    result = gateway.send_command(
        {
            "command_id": "command-1",
            "session_id": "session-1",
            "phase_version": 5,
            "command": "START_PROXY_MEETING",
            "issued_at": "2026-07-26T10:00:00Z",
            "payload": {},
        }
    )

    assert result["accepted"] is True
    method, url, options = transport.calls[0]
    assert (method, url) == (
        "POST",
        "http://media-service:8000/internal/commands",
    )
    assert options["headers"]["Authorization"] == "Bearer service-secret"
    assert options["timeout"] == 4


def test_http_gateway_converts_network_errors():
    class FailingSession:
        def request(self, *args, **kwargs):
            raise requests.Timeout("media timeout")

    gateway = HttpMediaGateway(
        "http://media-service:8000", "service-secret", session=FailingSession()
    )
    with pytest.raises(MediaGatewayError, match="media timeout"):
        gateway.get_status("session-1")


def test_http_gateway_returns_export_bytes():
    transport = FakeSession()
    transport.response = FakeResponse(content=b"PK-media")
    gateway = HttpMediaGateway(
        "http://media-service:8000", "service-secret", session=transport
    )
    assert gateway.export_bundle("session-1") == b"PK-media"


def test_http_gateway_reports_rtc_metrics_to_b():
    transport = FakeSession()
    transport.response = FakeResponse({"accepted": True, "sample_count": 1})
    gateway = HttpMediaGateway(
        "http://media-service:8000", "service-secret", session=transport
    )

    result = gateway.report_rtc_metrics(
        {
            "session_id": "session-1",
            "phase_version": 2,
            "participant_id": "principal-1",
            "role": "principal",
            "samples": [{"rtt_ms": 30}],
        }
    )

    method, url, options = transport.calls[0]
    assert result["accepted"] is True
    assert (method, url) == (
        "POST",
        "http://media-service:8000/internal/rtc-metrics",
    )
    assert options["json"]["participant_id"] == "principal-1"
