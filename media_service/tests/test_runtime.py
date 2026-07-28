from __future__ import annotations

import pytest

from media_service.app.runtime import RuntimeCoordinator


class FakeLiveKit:
    def __init__(self):
        self.rooms = []
        self.proxy_connections = []
        self.recorder_connections = []
        self.disconnects = []
        self.calls = []

    async def ensure_room(self, room_name):
        self.rooms.append(room_name)

    async def connect_proxy(self, session_id, runtime_id, phase_version, room_name):
        self.calls.append("connect_proxy")
        self.proxy_connections.append((session_id, room_name))

    async def connect_recorder(self, session_id, runtime_id, phase_version, room_name):
        self.calls.append("connect_recorder")
        self.recorder_connections.append((session_id, room_name))

    async def disconnect(self, session_id):
        self.calls.append("disconnect")
        self.disconnects.append(session_id)


class FakeLifecycle:
    def __init__(self, calls):
        self.calls = calls

    async def start_session(
        self,
        session_id,
        runtime_id,
        context,
        *,
        proxy_enabled,
        artifact_version,
    ):
        pass

    async def finalize(self, session_id, phase_version):
        self.calls.append("finalize")

    async def cancel(self, session_id):
        self.calls.append("cancel")

    async def regenerate_summary(self, session_id, phase_version, payload):
        pass


@pytest.mark.asyncio
async def test_start_proxy_is_singleton_and_reports_ready(repository):
    livekit = FakeLiveKit()
    coordinator = RuntimeCoordinator(repository, livekit)

    first = await coordinator.start_proxy("session-1", 5, {"materials": []})
    second = await coordinator.start_proxy("session-1", 5, {"materials": []})

    assert first.runtime_id == second.runtime_id
    assert len(livekit.proxy_connections) == 1
    assert repository.pending_outbox()[0].event_type == "MEDIA_READY"


@pytest.mark.asyncio
async def test_handoff_disconnects_proxy_before_event(repository):
    livekit = FakeLiveKit()
    coordinator = RuntimeCoordinator(repository, livekit, FakeLifecycle(livekit.calls))
    await coordinator.start_proxy("session-1", 5, {})

    for index, role in enumerate(("principal", "teammate_1", "teammate_2"), 1):
        repository.record_connection(
            session_id="session-1",
            runtime_id="preflight:session-1:v1",
            participant_id=f"participant-{index}",
            role=role,
            state="ready",
            device_metadata={"kind": "audioinput"},
        )

    await coordinator.begin_handoff("session-1", 9)

    assert livekit.disconnects == ["session-1"]
    assert livekit.calls[-2:] == ["cancel", "disconnect"]
    assert repository.pending_outbox()[-1].event_type == "HANDOFF_COMPLETE"


@pytest.mark.asyncio
async def test_sync_room_connects_hidden_recorder_and_never_proxy(repository):
    livekit = FakeLiveKit()
    coordinator = RuntimeCoordinator(repository, livekit)

    runtime = await coordinator.start_sync("session-1", 10)

    assert runtime.room_kind == "sync"
    assert livekit.proxy_connections == []
    assert livekit.recorder_connections == [("session-1", runtime.room_name)]


@pytest.mark.asyncio
async def test_explicit_end_emits_one_meeting_ended(repository):
    livekit = FakeLiveKit()
    coordinator = RuntimeCoordinator(repository, livekit, FakeLifecycle(livekit.calls))
    await coordinator.start_proxy("session-1", 5, {})

    await coordinator.end_current("session-1", 5)
    await coordinator.end_current("session-1", 5)

    assert livekit.calls[-2:] == ["finalize", "disconnect"]
    ended = [
        row for row in repository.pending_outbox() if row.event_type == "MEETING_ENDED"
    ]
    assert len(ended) == 1


@pytest.mark.asyncio
async def test_handoff_waits_for_all_human_device_checks(repository):
    livekit = FakeLiveKit()
    coordinator = RuntimeCoordinator(repository, livekit)
    repository.record_connection(
        session_id="session-1",
        runtime_id="preflight:session-1:v1",
        participant_id="p-1",
        role="principal",
        state="ready",
        device_metadata={},
    )

    with pytest.raises(RuntimeError, match="media ready"):
        await coordinator.begin_handoff("session-1", 9)

    assert all(
        row.event_type != "HANDOFF_COMPLETE" for row in repository.pending_outbox()
    )


@pytest.mark.asyncio
async def test_restart_reconciles_existing_runtime_without_creating_another(repository):
    first_livekit = FakeLiveKit()
    first = RuntimeCoordinator(repository, first_livekit)
    runtime = await first.start_proxy("session-1", 5, {"materials": []})

    recovered_livekit = FakeLiveKit()
    recovered = RuntimeCoordinator(repository, recovered_livekit)
    await recovered.reconcile()

    runtimes = repository.list_session_runtimes("session-1")
    assert [item.runtime_id for item in runtimes] == [runtime.runtime_id]
    assert recovered_livekit.proxy_connections == [
        ("session-1", runtime.room_name)
    ]


@pytest.mark.asyncio
async def test_restart_reconnects_sync_recorder(repository):
    first = RuntimeCoordinator(repository, FakeLiveKit())
    runtime = await first.start_sync("session-1", 10)

    recovered_livekit = FakeLiveKit()
    await RuntimeCoordinator(repository, recovered_livekit).reconcile()

    assert recovered_livekit.recorder_connections == [
        ("session-1", runtime.room_name)
    ]


@pytest.mark.asyncio
async def test_participant_connection_is_persisted_and_emitted(repository):
    coordinator = RuntimeCoordinator(repository, FakeLiveKit())
    runtime = await coordinator.start_sync("session-1", 10)

    await coordinator.participant_state_changed(
        "session-1",
        "participant-1",
        "teammate_1",
        "connected",
        {"room_name": runtime.room_name},
    )

    connection = repository.list_session_connections("session-1")[-1]
    assert (connection.participant_id, connection.state) == (
        "participant-1",
        "connected",
    )
    event = repository.pending_outbox()[-1]
    assert event.event_type == "PARTICIPANT_JOINED"
    assert event.payload["role"] == "teammate_1"
