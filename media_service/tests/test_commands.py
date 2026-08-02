import asyncio

import pytest
from fastapi.testclient import TestClient

from media_service.app.commands import CommandService
from media_service.app.config import Settings
from media_service.app.main import create_app
from media_service.app.schemas import CommandEnvelope


def _client(settings_overrides=None, **app_options):
    app_options.setdefault("runtime_coordinator", FakeRuntime())
    settings = Settings(
        media_database_url="sqlite+pysqlite:///:memory:",
        media_database_schema="study1_media",
        a_to_b_service_token="a-secret",
        study1_internal_api_key="b-secret",
        a_base_url="http://backend:5000",
        livekit_url="ws://livekit:7880",
        livekit_api_key="devkey",
        livekit_api_secret="test-livekit-secret-at-least-32-bytes",
        **(settings_overrides or {}),
    )
    return TestClient(create_app(settings, **app_options))


def test_command_requires_service_bearer(command_payload):
    response = _client().post("/internal/commands", json=command_payload)
    assert response.status_code == 401


def test_command_replay_returns_original_result(command_payload):
    runtime = FakeRuntime()
    client = _client(runtime_coordinator=runtime)
    execution_count = 0
    execute = client.app.state.command_service.execute

    async def counted_execute(command_id):
        nonlocal execution_count
        execution_count += 1
        await execute(command_id)

    client.app.state.command_service.execute = counted_execute
    headers = {"Authorization": "Bearer a-secret"}
    first = client.post("/internal/commands", headers=headers, json=command_payload)
    replay = client.post("/internal/commands", headers=headers, json=command_payload)

    assert first.status_code == replay.status_code == 202
    assert first.json()["duplicate"] is False
    assert replay.json()["duplicate"] is True
    assert replay.json()["command_id"] == command_payload["command_id"]
    assert execution_count == 1


def test_unsupported_command_is_rejected(command_payload):
    command_payload["command"] = "AUTO_START_SESSION"
    response = _client().post(
        "/internal/commands",
        headers={"Authorization": "Bearer a-secret"},
        json=command_payload,
    )
    assert response.status_code == 422


def test_start_proxy_rejects_missing_authorized_context(command_payload):
    command_payload["payload"] = {}
    response = _client().post(
        "/internal/commands",
        headers={"Authorization": "Bearer a-secret"},
        json=command_payload,
    )
    assert response.status_code == 422


class FakeRuntime:
    def __init__(self):
        self.calls = []

    async def start_proxy(self, session_id, phase_version, config):
        self.calls.append(("start_proxy", session_id, phase_version, config))

    async def start_sync(self, session_id, phase_version):
        self.calls.append(("start_sync", session_id, phase_version))

    async def begin_handoff(self, session_id, phase_version):
        self.calls.append(("handoff", session_id, phase_version))

    async def end_current(self, session_id, phase_version):
        self.calls.append(("end", session_id, phase_version))

    async def stop_session(self, session_id, phase_version):
        self.calls.append(("stop", session_id, phase_version))

    async def regenerate_summary(self, session_id, phase_version, payload):
        self.calls.append(("regenerate", session_id, phase_version, payload))


def test_accepted_start_command_runs_after_persistence(command_payload):
    runtime = FakeRuntime()
    client = _client(runtime_coordinator=runtime)

    response = client.post(
        "/internal/commands",
        headers={"Authorization": "Bearer a-secret"},
        json=command_payload,
    )

    assert response.status_code == 202
    assert runtime.calls == [
        (
            "start_proxy",
            command_payload["session_id"],
            5,
            command_payload["payload"]["authorized_context"],
        )
    ]


@pytest.mark.asyncio
async def test_stop_session_dispatches_dedicated_cleanup(repository, command_payload):
    command_payload["command"] = "STOP_SESSION"
    command_payload["payload"] = {}
    envelope = CommandEnvelope.model_validate(command_payload)
    runtime = FakeRuntime()

    await CommandService(repository, runtime).dispatch(envelope)

    assert runtime.calls == [
        ("stop", envelope.session_id, envelope.phase_version)
    ]


@pytest.mark.asyncio
async def test_restart_dispatches_an_accepted_command(repository, command_payload):
    envelope = CommandEnvelope.model_validate(command_payload)
    accepted = CommandService(repository).accept(envelope)
    runtime = FakeRuntime()

    await CommandService(repository, runtime).reconcile_pending()

    assert runtime.calls == [
        (
            "start_proxy",
            envelope.session_id,
            envelope.phase_version,
            envelope.payload["authorized_context"],
        )
    ]
    assert repository.get_command(accepted.command_id).status == "completed"


@pytest.mark.asyncio
async def test_restart_retries_a_failed_command(repository, command_payload):
    envelope = CommandEnvelope.model_validate(command_payload)
    accepted = CommandService(repository).accept(envelope)
    repository.mark_command_status(accepted.command_id, "failed", error_code="Timeout")
    runtime = FakeRuntime()

    await CommandService(repository, runtime).reconcile_pending()

    assert len(runtime.calls) == 1
    row = repository.get_command(accepted.command_id)
    assert row.status == "completed"
    assert row.error_code is None


@pytest.mark.asyncio
async def test_concurrent_execution_claims_persisted_command_once(
    repository, command_payload
):
    class BlockingRuntime(FakeRuntime):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def start_proxy(self, session_id, phase_version, config):
            self.calls.append(("start_proxy", session_id, phase_version, config))
            self.started.set()
            await self.release.wait()

    envelope = CommandEnvelope.model_validate(command_payload)
    runtime = BlockingRuntime()
    service = CommandService(repository, runtime)
    accepted = service.accept(envelope)
    first = asyncio.create_task(service.execute(accepted.command_id))
    await runtime.started.wait()
    second = asyncio.create_task(service.execute(accepted.command_id))

    try:
        await asyncio.sleep(0)
        assert len(runtime.calls) == 1
    finally:
        runtime.release.set()
        await asyncio.gather(first, second)

    assert repository.get_command(accepted.command_id).status == "completed"


def test_status_and_export_require_a_service_token(command_payload):
    client = _client()
    session_id = command_payload["session_id"]
    assert client.get(f"/internal/sessions/{session_id}/status").status_code == 401
    assert client.get(f"/internal/sessions/{session_id}/export").status_code == 401

    headers = {"Authorization": "Bearer a-secret"}
    status_response = client.get(
        f"/internal/sessions/{session_id}/status", headers=headers
    )
    export_response = client.get(
        f"/internal/sessions/{session_id}/export", headers=headers
    )
    assert status_response.status_code == 200
    assert status_response.json()["session_id"] == session_id
    assert export_response.status_code == 200
    assert export_response.headers["content-type"] == "application/zip"


def test_status_pending_callback_count_is_session_scoped():
    client = _client()
    client.app.state.repository.enqueue_event("session-1", 1, "MEDIA_READY", {})
    client.app.state.repository.enqueue_event("session-2", 1, "MEDIA_READY", {})

    response = client.get(
        "/internal/sessions/session-1/status",
        headers={"Authorization": "Bearer a-secret"},
    )

    assert response.json()["pending_callback_count"] == 1


def test_recording_replay_is_session_scoped_and_supports_range(tmp_path):
    session_root = tmp_path / "session-1"
    session_root.mkdir()
    (session_root / "teammate_1.wav").write_bytes(b"0123456789")
    client = _client(settings_overrides={"media_root": str(tmp_path)})
    headers = {
        "Authorization": "Bearer a-secret",
        "Range": "bytes=2-5",
    }

    response = client.get(
        "/internal/sessions/session-1/recordings/teammate_1.wav",
        headers=headers,
    )

    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert client.get(
        "/internal/sessions/session-2/recordings/teammate_1.wav",
        headers=headers,
    ).status_code == 404


def test_device_status_is_authenticated_and_persisted():
    client = _client()
    payload = {
        "session_id": "session-1",
        "phase_version": 1,
        "participant_id": "participant-1",
        "role": "principal",
        "state": "ready",
        "device": {"kind": "audioinput", "label": "USB microphone"},
    }
    assert client.post("/internal/device-status", json=payload).status_code == 401

    response = client.post(
        "/internal/device-status",
        headers={"Authorization": "Bearer a-secret"},
        json=payload,
    )
    assert response.status_code == 202
    status = client.get(
        "/internal/sessions/session-1/status",
        headers={"Authorization": "Bearer a-secret"},
    ).json()
    assert status["connections"] == [
        {
            "participant_id": "participant-1",
            "role": "principal",
            "state": "ready",
            "device": {"kind": "audioinput", "label": "USB microphone"},
        }
    ]
