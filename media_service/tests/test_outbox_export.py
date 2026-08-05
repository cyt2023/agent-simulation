from __future__ import annotations

import io
import zipfile

import httpx
import pytest

from media_service.app.callbacks import CallbackClient
from media_service.app.export import build_media_export


@pytest.mark.asyncio
async def test_callback_failure_is_retained_for_retry(repository):
    message = repository.enqueue_event("session-1", 5, "MEDIA_READY", {})

    def fail(request):
        return httpx.Response(503, request=request)

    client = CallbackClient(
        repository,
        "http://workflow",
        "internal-secret",
        transport=httpx.MockTransport(fail),
    )
    delivered = await client.deliver(message)

    assert delivered is False
    pending = repository.pending_outbox()
    assert pending[0].attempt_count == 1
    assert "503" in pending[0].last_error


@pytest.mark.asyncio
async def test_callback_uses_only_a_internal_endpoint_and_key(repository):
    message = repository.enqueue_event("session-1", 5, "MEDIA_READY", {})
    seen = {}

    def accept(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-Study1-Internal-Key")
        return httpx.Response(200, json={"accepted": True}, request=request)

    client = CallbackClient(
        repository,
        "http://workflow",
        "internal-secret",
        transport=httpx.MockTransport(accept),
    )
    assert await client.deliver(message) is True
    assert seen == {
        "url": "http://workflow/api/internal/study1/media-events",
        "key": "internal-secret",
    }
    assert repository.pending_outbox() == []


@pytest.mark.asyncio
async def test_stale_callback_is_audited_and_not_retried(repository):
    message = repository.enqueue_event("session-1", 5, "MEDIA_READY", {})

    def stale(request):
        return httpx.Response(409, json={"error": "STALE_MEDIA_EVENT"}, request=request)

    client = CallbackClient(
        repository,
        "http://workflow",
        "internal-secret",
        transport=httpx.MockTransport(stale),
    )

    assert await client.deliver(message) is False
    assert repository.pending_outbox() == []
    stored = repository.list_session_outbox("session-1")[0]
    assert stored.attempt_count == 1
    assert "stale" in stored.last_error.lower()


def test_export_is_scoped_to_requested_session(repository):
    repository.enqueue_event("session-1", 5, "MEDIA_READY", {"room": "one"})
    repository.enqueue_event("session-2", 5, "MEDIA_READY", {"room": "two"})

    payload = build_media_export(repository, "session-1")

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        outbox = archive.read("runtime_events.jsonl").decode("utf-8")
        status = archive.read("media_status.json").decode("utf-8")
    assert "session-1" in outbox
    assert "session-2" not in outbox
    assert "session-1" in status


def test_export_contains_proxy_agent_log(repository):
    for segment_id, speaker, text in (
        ("human-1", "teammate_1", "Human statement"),
        ("proxy-1", "proxy", "Proxy response"),
    ):
        repository.add_transcript_segment(
            segment_id=segment_id,
            session_id="session-1",
            runtime_id="runtime-1",
            speaker=speaker,
            start_ms=0,
            end_ms=100,
            text=text,
            confidence=None,
            is_final=True,
            provider_version="provider-v1",
        )

    payload = build_media_export(repository, "session-1")

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        agent_log = archive.read("agent_log.jsonl").decode("utf-8")
        minutes = archive.read("meeting_minutes.md").decode("utf-8")
    assert "proxy-1" in agent_log
    assert "Proxy response" in agent_log
    assert "human-1" not in agent_log
    assert "Human · Teammate 1 (T1)" in minutes
    assert "AI Proxy (X)" in minutes
    assert minutes.index("Human statement") < minutes.index("Proxy response")
