from __future__ import annotations

import pytest

from media_service.app.room_policy import HandoffBarrier, RoomPolicySnapshot
from media_service.app.runtime import RuntimeCoordinator
from media_service.app.schemas import RuntimeState


class FakeLiveKit:
    def __init__(self):
        self.rooms = []
        self.proxy_connections = []
        self.recorder_connections = []
        self.disconnects = []
        self.calls = []
        self.room_snapshot = RoomPolicySnapshot(
            connected_roles=frozenset(),
            proxy_present=False,
            can_publish_by_role={},
        )

    async def ensure_room(self, room_name):
        self.rooms.append(room_name)

    async def connect_proxy(self, session_id, runtime_id, phase_version, room_name):
        self.calls.append("connect_proxy")
        self.proxy_connections.append((session_id, room_name))

    async def connect_recorder(self, session_id, runtime_id, phase_version, room_name):
        self.calls.append("connect_recorder")
        connection = (session_id, room_name)
        if connection not in self.recorder_connections:
            self.recorder_connections.append(connection)

    async def disconnect(self, session_id):
        self.calls.append("disconnect")
        self.disconnects.append(session_id)

    async def disconnect_proxy(self, session_id):
        self.calls.append("disconnect_proxy")
        self.disconnects.append((session_id, "proxy"))

    async def apply_speaking_policy(self, session_id, room_name, policy):
        self.calls.append(("policy", policy, room_name))
        return self.room_snapshot


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


def _mark_humans_ready(repository, session_id="session-1"):
    for index, role in enumerate(("principal", "teammate_1", "teammate_2"), 1):
        repository.record_connection(
            session_id=session_id,
            runtime_id=f"preflight:{session_id}:v1",
            participant_id=f"participant-{index}",
            role=role,
            state="ready",
            device_metadata={"kind": "audioinput"},
        )


def _handoff_ready_snapshot():
    return RoomPolicySnapshot(
        connected_roles=frozenset({"principal", "teammate_1", "teammate_2"}),
        proxy_present=False,
        can_publish_by_role={
            "principal": False,
            "teammate_1": False,
            "teammate_2": False,
        },
    )


def test_handoff_barrier_requires_humans_proxy_absence_and_muted_rights():
    barrier = HandoffBarrier("session-1", phase_version=9)

    assert barrier.observe(
        RoomPolicySnapshot(
            connected_roles=frozenset({"teammate_1", "teammate_2"}),
            proxy_present=False,
            can_publish_by_role={"teammate_1": False, "teammate_2": False},
        )
    ) is False
    assert barrier.observe(
        RoomPolicySnapshot(
            connected_roles=frozenset({"principal", "teammate_1", "teammate_2"}),
            proxy_present=True,
            can_publish_by_role={
                "principal": False,
                "teammate_1": False,
                "teammate_2": False,
            },
        )
    ) is False
    assert barrier.observe(
        RoomPolicySnapshot(
            connected_roles=frozenset({"principal", "teammate_1", "teammate_2"}),
            proxy_present=False,
            can_publish_by_role={
                "principal": False,
                "teammate_1": True,
                "teammate_2": False,
            },
        )
    ) is False
    assert barrier.observe(
        RoomPolicySnapshot(
            connected_roles=frozenset({"principal", "teammate_1", "teammate_2"}),
            proxy_present=False,
            can_publish_by_role={
                "principal": False,
                "teammate_1": False,
                "teammate_2": False,
            },
        )
    ) is True


@pytest.mark.asyncio
async def test_start_proxy_is_singleton_and_reports_ready(repository):
    livekit = FakeLiveKit()
    coordinator = RuntimeCoordinator(repository, livekit)

    first = await coordinator.start_proxy("session-1", 5, {"materials": []})
    second = await coordinator.start_proxy("session-1", 5, {"materials": []})

    assert first.runtime_id == second.runtime_id
    assert first.room_name == "study1-session-1-audio"
    assert livekit.recorder_connections == [
        ("session-1", "study1-session-1-audio")
    ]
    assert len(livekit.proxy_connections) == 1
    assert repository.pending_outbox()[0].event_type == "MEDIA_READY"


@pytest.mark.asyncio
async def test_handoff_completes_only_after_room_snapshot_satisfies_barrier(repository):
    livekit = FakeLiveKit()
    coordinator = RuntimeCoordinator(repository, livekit, FakeLifecycle(livekit.calls))
    await coordinator.start_proxy("session-1", 5, {})

    _mark_humans_ready(repository)

    await coordinator.end_current("session-1", 5)
    livekit.room_snapshot = RoomPolicySnapshot(
        connected_roles=frozenset({"teammate_1", "teammate_2"}),
        proxy_present=False,
        can_publish_by_role={"teammate_1": False, "teammate_2": False},
    )
    await coordinator.begin_handoff("session-1", 9)

    assert all(
        row.event_type != "HANDOFF_COMPLETE" for row in repository.pending_outbox()
    )

    livekit.room_snapshot = _handoff_ready_snapshot()
    await coordinator.participant_state_changed(
        "session-1",
        "participant-1",
        "principal",
        "connected",
        {"room_name": "study1-session-1-audio"},
    )
    await coordinator.participant_state_changed(
        "session-1",
        "participant-1",
        "principal",
        "connected",
        {"room_name": "study1-session-1-audio"},
    )

    completed = [
        row for row in repository.pending_outbox()
        if row.event_type == "HANDOFF_COMPLETE"
    ]
    assert len(completed) == 1
    payload = dict(completed[0].payload)
    assert payload.pop("principal_joined_at").endswith("Z")
    assert payload.pop("proxy_stopped_at").endswith("Z")
    assert payload == {
        "runtime_id": repository.list_session_runtimes("session-1")[0].runtime_id,
        "proxy_disconnected": True,
        "sync_room_ready": True,
        "room_name": "study1-session-1-audio",
        "connected_roles": ["principal", "teammate_1", "teammate_2"],
        "can_publish_by_role": {
            "principal": False,
            "teammate_1": False,
            "teammate_2": False,
        },
    }
    assert completed[0].phase_version == 9
    proxy_runtime = repository.list_session_runtimes("session-1")[0]
    assert proxy_runtime.state == "STOPPED"
    assert proxy_runtime.ended_at is not None


@pytest.mark.asyncio
async def test_active_runtime_retry_repairs_missing_media_ready_event(repository):
    runtime, _ = repository.get_or_create_runtime(
        runtime_id="proxy-runtime",
        session_id="session-1",
        phase_version=5,
        room_kind="proxy",
        room_name="study1-session-1-audio",
        state=RuntimeState.ACTIVE,
        runtime_config={"materials": []},
    )
    assert repository.pending_outbox() == []

    returned = await RuntimeCoordinator(repository, FakeLiveKit()).start_proxy(
        "session-1", 5, {"materials": []}
    )

    assert returned.runtime_id == runtime.runtime_id
    ready = [
        row for row in repository.pending_outbox()
        if row.event_type == "MEDIA_READY"
    ]
    assert len(ready) == 1
    assert ready[0].payload["runtime_id"] == runtime.runtime_id


def test_runtime_event_key_is_deterministic_and_exactly_once(repository):
    runtime, _ = repository.get_or_create_runtime(
        runtime_id="proxy-runtime",
        session_id="session-1",
        phase_version=5,
        room_kind="proxy",
        room_name="study1-session-1-audio",
        state=RuntimeState.HANDING_OFF,
        runtime_config={},
    )
    payload = {"runtime_id": runtime.runtime_id}

    repository.finish_runtime_with_event(
        runtime.runtime_id,
        state=RuntimeState.STOPPED,
        session_id="session-1",
        phase_version=9,
        event_type="HANDOFF_COMPLETE",
        payload=payload,
    )
    repository.finish_runtime_with_event(
        runtime.runtime_id,
        state=RuntimeState.STOPPED,
        session_id="session-1",
        phase_version=9,
        event_type="HANDOFF_COMPLETE",
        payload=payload,
    )

    completed = [
        row for row in repository.list_session_outbox("session-1")
        if row.event_type == "HANDOFF_COMPLETE"
    ]
    assert len(completed) == 1


@pytest.mark.asyncio
async def test_sync_room_connects_hidden_recorder_and_never_proxy(repository):
    livekit = FakeLiveKit()
    coordinator = RuntimeCoordinator(repository, livekit)

    runtime = await coordinator.start_sync("session-1", 10)

    assert runtime.room_kind == "sync"
    assert livekit.proxy_connections == []
    assert livekit.recorder_connections == [("session-1", runtime.room_name)]


@pytest.mark.asyncio
async def test_proxy_end_removes_x_but_preserves_recorder_and_room(repository):
    livekit = FakeLiveKit()
    coordinator = RuntimeCoordinator(repository, livekit, FakeLifecycle(livekit.calls))
    await coordinator.start_proxy("session-1", 5, {})

    await coordinator.end_current("session-1", 5)
    await coordinator.end_current("session-1", 5)

    assert livekit.calls.count("finalize") == 1
    assert livekit.calls.count("disconnect_proxy") == 1
    assert "disconnect" not in livekit.calls
    assert livekit.recorder_connections == [
        ("session-1", "study1-session-1-audio")
    ]
    runtime = repository.list_session_runtimes("session-1")[0]
    assert runtime.state == "HANDING_OFF"
    assert runtime.ended_at is None
    ended = [
        row for row in repository.pending_outbox() if row.event_type == "MEETING_ENDED"
    ]
    assert len(ended) == 1


@pytest.mark.asyncio
async def test_future_sync_end_is_retryable_while_proxy_handoff_is_still_active(
    repository,
):
    livekit = FakeLiveKit()
    coordinator = RuntimeCoordinator(repository, livekit, FakeLifecycle(livekit.calls))
    await coordinator.start_proxy("session-1", 5, {})
    await coordinator.end_current("session-1", 5)

    with pytest.raises(RuntimeError, match="Sync meeting is not active"):
        await coordinator.end_current("session-1", 11)

    runtime = repository.active_runtime("session-1")
    assert runtime.room_kind == "proxy"
    assert runtime.state == "HANDING_OFF"


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
async def test_restart_with_open_sync_terminates_legacy_proxy_runtime(repository):
    proxy, _ = repository.get_or_create_runtime(
        runtime_id="legacy-proxy",
        session_id="session-1",
        phase_version=5,
        room_kind="proxy",
        room_name="study1-session-1-audio",
        state=RuntimeState.HANDING_OFF,
        runtime_config={"handoff_phase_version": 9},
    )
    repository.get_or_create_runtime(
        runtime_id="active-sync",
        session_id="session-1",
        phase_version=10,
        room_kind="sync",
        room_name="study1-session-1-audio",
        state=RuntimeState.ACTIVE,
        runtime_config={"proxy_enabled": False},
    )
    livekit = FakeLiveKit()

    await RuntimeCoordinator(repository, livekit).reconcile()

    restored_proxy = next(
        row
        for row in repository.list_session_runtimes("session-1")
        if row.runtime_id == proxy.runtime_id
    )
    assert restored_proxy.state == "STOPPED"
    assert restored_proxy.ended_at is not None
    assert livekit.proxy_connections == []
    assert livekit.recorder_connections == [
        ("session-1", "study1-session-1-audio")
    ]


@pytest.mark.asyncio
async def test_restart_rebuilds_pending_handoff_barrier_without_reviving_proxy(
    repository,
):
    initial_livekit = FakeLiveKit()
    initial = RuntimeCoordinator(
        repository, initial_livekit, FakeLifecycle(initial_livekit.calls)
    )
    await initial.start_proxy("session-1", 5, {})
    _mark_humans_ready(repository)
    await initial.end_current("session-1", 5)
    await initial.begin_handoff("session-1", 9)

    recovered_livekit = FakeLiveKit()
    recovered = RuntimeCoordinator(repository, recovered_livekit)
    await recovered.reconcile()

    assert recovered_livekit.proxy_connections == []
    recovered_livekit.room_snapshot = _handoff_ready_snapshot()
    await recovered.participant_state_changed(
        "session-1",
        "participant-1",
        "principal",
        "connected",
        {"room_name": "study1-session-1-audio"},
    )
    await recovered.participant_state_changed(
        "session-1",
        "participant-1",
        "principal",
        "connected",
        {"room_name": "study1-session-1-audio"},
    )

    completed = [
        row
        for row in repository.list_session_outbox("session-1")
        if row.event_type == "HANDOFF_COMPLETE"
    ]
    assert len(completed) == 1
    assert completed[0].phase_version == 9
    proxy_runtime = repository.list_session_runtimes("session-1")[0]
    assert proxy_runtime.state == "STOPPED"
    assert proxy_runtime.ended_at is not None


@pytest.mark.asyncio
async def test_start_sync_reuses_recorder_applies_policy_and_ends_proxy(repository):
    livekit = FakeLiveKit()
    coordinator = RuntimeCoordinator(repository, livekit, FakeLifecycle(livekit.calls))
    proxy = await coordinator.start_proxy("session-1", 5, {})

    sync = await coordinator.start_sync("session-1", 10)

    runtimes = repository.list_session_runtimes("session-1")
    restored_proxy = next(row for row in runtimes if row.runtime_id == proxy.runtime_id)
    assert restored_proxy.state == "STOPPED"
    assert restored_proxy.ended_at is not None
    assert sync.state == "ACTIVE"
    assert livekit.recorder_connections == [
        ("session-1", "study1-session-1-audio")
    ]
    assert "disconnect" not in livekit.calls
    assert "disconnect_proxy" in livekit.calls
    assert (
        "policy",
        "sync",
        "study1-session-1-audio",
    ) in livekit.calls

    recovered_livekit = FakeLiveKit()
    await RuntimeCoordinator(repository, recovered_livekit).reconcile()
    assert recovered_livekit.proxy_connections == []
    assert recovered_livekit.recorder_connections == [
        ("session-1", "study1-session-1-audio")
    ]


@pytest.mark.asyncio
async def test_stop_session_closes_media_and_ends_every_open_runtime(repository):
    proxy, _ = repository.get_or_create_runtime(
        runtime_id="proxy-runtime",
        session_id="session-1",
        phase_version=5,
        room_kind="proxy",
        room_name="study1-session-1-audio",
        state=RuntimeState.HANDING_OFF,
        runtime_config={"handoff_phase_version": 9},
    )
    sync, _ = repository.get_or_create_runtime(
        runtime_id="sync-runtime",
        session_id="session-1",
        phase_version=10,
        room_kind="sync",
        room_name="study1-session-1-audio",
        state=RuntimeState.ACTIVE,
        runtime_config={"proxy_enabled": False},
    )
    livekit = FakeLiveKit()
    coordinator = RuntimeCoordinator(repository, livekit, FakeLifecycle(livekit.calls))

    await coordinator.stop_session("session-1", 11)

    assert livekit.calls.count("cancel") == 1
    assert livekit.calls.count("disconnect") == 1
    runtimes = repository.list_session_runtimes("session-1")
    assert {row.runtime_id for row in runtimes} == {
        proxy.runtime_id,
        sync.runtime_id,
    }
    assert all(row.state == "STOPPED" for row in runtimes)
    assert all(row.ended_at is not None for row in runtimes)


@pytest.mark.asyncio
async def test_finalize_error_disconnects_recorder_and_ends_runtime(repository):
    livekit = FakeLiveKit()

    class FailingLifecycle(FakeLifecycle):
        async def finalize(self, session_id, phase_version):
            self.calls.append("finalize")
            raise RuntimeError("artifact flush failed")

    coordinator = RuntimeCoordinator(repository, livekit, FailingLifecycle(livekit.calls))
    await coordinator.start_proxy("session-1", 5, {})

    with pytest.raises(RuntimeError, match="artifact flush failed"):
        await coordinator.end_current("session-1", 5)

    assert livekit.calls.count("disconnect") == 1
    runtime = repository.list_session_runtimes("session-1")[0]
    assert runtime.state == "ERROR"
    assert runtime.ended_at is not None


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
