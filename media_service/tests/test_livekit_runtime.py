from types import SimpleNamespace

import pytest
from livekit import rtc

from media_service.app.config import Settings
from media_service.app.livekit_runtime import LiveKitRoomRuntime
from media_service.app.playback import ProxyPlaybackController
from media_service.app.room_policy import SpeakingPolicy


def _settings():
    return Settings(
        media_database_url="sqlite+pysqlite:///:memory:",
        media_database_schema="study1_media",
        a_to_b_service_token="a-secret",
        study1_internal_api_key="b-secret",
        livekit_api_key="devkey",
        livekit_api_secret="test-livekit-secret-at-least-32-bytes",
    )


@pytest.mark.asyncio
async def test_livekit_participant_events_are_forwarded_with_authoritative_role():
    seen = []

    async def consume(session_id, participant_id, role, state, metadata):
        seen.append((session_id, participant_id, role, state, metadata))

    runtime = LiveKitRoomRuntime(_settings(), connection_consumer=consume)

    await runtime._emit_connection(
        "session-1",
        "study1-session-1-sync-v10",
        SimpleNamespace(identity="participant-1", name="teammate_1"),
        "connected",
    )

    assert seen == [
        (
            "session-1",
            "participant-1",
            "teammate_1",
            "connected",
            {"room_name": "study1-session-1-sync-v10"},
        )
    ]


@pytest.mark.asyncio
async def test_disconnecting_proxy_preserves_stable_recorder_connection():
    class FakeRoom:
        def __init__(self):
            self.disconnect_count = 0

        async def disconnect(self):
            self.disconnect_count += 1

    runtime = LiveKitRoomRuntime(_settings())
    recorder = FakeRoom()
    proxy = FakeRoom()
    runtime._recorder_rooms["session-1"] = recorder
    runtime._proxy_rooms["session-1"] = proxy

    await runtime.disconnect_proxy("session-1")

    assert proxy.disconnect_count == 1
    assert recorder.disconnect_count == 0

    await runtime.disconnect("session-1")

    assert recorder.disconnect_count == 1


@pytest.mark.asyncio
async def test_runtime_barge_in_clears_source_queue_and_rejects_late_frames():
    class FakeAudioSource:
        def __init__(self):
            self.clear_queue_count = 0
            self.captured = []

        async def clear_queue(self):
            self.clear_queue_count += 1

        async def capture_frame(self, frame):
            self.captured.append(frame)

    runtime = LiveKitRoomRuntime(_settings())
    source = FakeAudioSource()
    runtime._sources["session-1"] = source
    runtime._playbacks["session-1"] = ProxyPlaybackController(source)

    generation = runtime.begin_proxy_audio("session-1", "turn-1")
    await runtime.interrupt_proxy_audio("session-1")
    published = await runtime.publish_audio(
        "session-1", b"\x01\x00" * 240, generation=generation
    )

    assert published is False
    assert source.clear_queue_count == 1
    assert source.captured == []


@pytest.mark.asyncio
async def test_recorder_and_proxy_use_separate_connection_roles():
    class ProbeRuntime(LiveKitRoomRuntime):
        def __init__(self, settings):
            super().__init__(settings)
            self.connect_calls = []

        async def _connect(
            self,
            session_id,
            room_name,
            *,
            access,
            publish_proxy,
            connection_kind,
            subscribe_audio,
        ):
            self.connect_calls.append(
                (session_id, room_name, connection_kind, subscribe_audio, publish_proxy)
            )

    runtime = ProbeRuntime(_settings())

    await runtime.connect_recorder("session-1", "runtime-1", 5, "study1-session-1-audio")
    await runtime.connect_proxy("session-1", "runtime-1", 5, "study1-session-1-audio")

    assert runtime.connect_calls == [
        ("session-1", "study1-session-1-audio", "recorder", True, False),
        ("session-1", "study1-session-1-audio", "proxy", False, True),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("policy", "expected_can_publish"),
    ((SpeakingPolicy.HANDOFF, False), (SpeakingPolicy.SYNC, True)),
)
async def test_real_adapter_applies_human_speaking_policy_and_removes_proxy(
    monkeypatch, policy, expected_can_publish
):
    participants = [
        SimpleNamespace(identity="p-1", name="principal"),
        SimpleNamespace(identity="t-1", name="teammate_1"),
        SimpleNamespace(identity="t-2", name="teammate_2"),
        SimpleNamespace(identity="proxy-session-1", name="proxy"),
        SimpleNamespace(identity="recorder-session-1", name="recorder"),
    ]

    class FakeRoomService:
        def __init__(self):
            self.updated = []
            self.removed = []

        async def list_participants(self, _request):
            return SimpleNamespace(participants=participants)

        async def update_participant(self, request):
            self.updated.append(request)

        async def remove_participant(self, request):
            self.removed.append(request)

    class FakeApiClient:
        instance = None

        def __init__(self, *_args):
            self.room = FakeRoomService()
            self.closed = False
            FakeApiClient.instance = self

        async def aclose(self):
            self.closed = True

    class FakeProxyRoom:
        def __init__(self):
            self.disconnect_count = 0

        async def disconnect(self):
            self.disconnect_count += 1

    monkeypatch.setattr(
        "media_service.app.livekit_runtime.api.LiveKitAPI", FakeApiClient
    )
    runtime = LiveKitRoomRuntime(_settings())
    proxy_room = FakeProxyRoom()
    runtime._proxy_rooms["session-1"] = proxy_room

    snapshot = await runtime.apply_speaking_policy(
        "session-1", "study1-session-1-audio", policy
    )

    client = FakeApiClient.instance
    assert client is not None
    assert client.closed is True
    assert proxy_room.disconnect_count == 1
    assert {request.identity for request in client.room.removed} == {
        "proxy-session-1"
    }
    assert {
        request.identity: request.permission.can_publish
        for request in client.room.updated
    } == {
        "p-1": expected_can_publish,
        "t-1": expected_can_publish,
        "t-2": expected_can_publish,
    }
    expected_sources = (
        [rtc.TrackSource.SOURCE_MICROPHONE] if expected_can_publish else []
    )
    assert all(
        list(request.permission.can_publish_sources) == expected_sources
        for request in client.room.updated
    )
    assert snapshot.connected_roles == frozenset(
        {"principal", "teammate_1", "teammate_2"}
    )
    assert snapshot.proxy_present is False
    assert snapshot.can_publish_by_role == {
        "principal": expected_can_publish,
        "teammate_1": expected_can_publish,
        "teammate_2": expected_can_publish,
    }


@pytest.mark.asyncio
async def test_recorder_disconnect_clears_connection_so_it_can_reconnect(monkeypatch):
    rooms = []

    class FakeRoom:
        def __init__(self):
            self.handlers = {}
            self.remote_participants = {}
            rooms.append(self)

        def on(self, event):
            def register(handler):
                self.handlers[event] = handler
                return handler

            return register

        async def connect(self, *_args):
            return None

    monkeypatch.setattr("media_service.app.livekit_runtime.rtc.Room", FakeRoom)
    runtime = LiveKitRoomRuntime(_settings())

    await runtime.connect_recorder(
        "session-1", "runtime-1", 5, "study1-session-1-audio"
    )
    rooms[0].handlers["disconnected"]("server_shutdown")
    await runtime.connect_recorder(
        "session-1", "runtime-2", 10, "study1-session-1-audio"
    )

    assert len(rooms) == 2
    assert runtime._recorder_rooms["session-1"] is rooms[1]


@pytest.mark.asyncio
async def test_existing_participant_callback_failure_disconnects_uncached_room(
    monkeypatch,
):
    rooms = []

    class FakeRoom:
        def __init__(self):
            self.handlers = {}
            self.remote_participants = {
                "p-1": SimpleNamespace(identity="p-1", name="principal")
            }
            self.disconnect_count = 0
            rooms.append(self)

        def on(self, event):
            def register(handler):
                self.handlers[event] = handler
                return handler

            return register

        async def connect(self, *_args):
            return None

        async def disconnect(self):
            self.disconnect_count += 1

    async def fail_connection(*_args):
        raise RuntimeError("connection callback failed")

    monkeypatch.setattr("media_service.app.livekit_runtime.rtc.Room", FakeRoom)
    runtime = LiveKitRoomRuntime(_settings(), connection_consumer=fail_connection)

    with pytest.raises(RuntimeError, match="connection callback failed"):
        await runtime.connect_recorder(
            "session-1", "runtime-1", 5, "study1-session-1-audio"
        )

    assert rooms[0].disconnect_count == 1
    assert "session-1" not in runtime._recorder_rooms


@pytest.mark.asyncio
async def test_proxy_publish_failure_is_not_cached_and_can_retry(monkeypatch):
    rooms = []
    should_fail = True

    class FakePublisher:
        async def publish_track(self, *_args):
            if should_fail:
                raise RuntimeError("publish failed")

    class FakeRoom:
        def __init__(self):
            self.handlers = {}
            self.remote_participants = {}
            self.local_participant = FakePublisher()
            self.disconnect_count = 0
            rooms.append(self)

        def on(self, event):
            def register(handler):
                self.handlers[event] = handler
                return handler

            return register

        async def connect(self, *_args):
            return None

        async def disconnect(self):
            self.disconnect_count += 1

    monkeypatch.setattr("media_service.app.livekit_runtime.rtc.Room", FakeRoom)
    monkeypatch.setattr(
        "media_service.app.livekit_runtime.rtc.AudioSource",
        lambda *_args: object(),
    )
    monkeypatch.setattr(
        "media_service.app.livekit_runtime.rtc.LocalAudioTrack",
        SimpleNamespace(create_audio_track=lambda *_args: object()),
    )
    monkeypatch.setattr(
        "media_service.app.livekit_runtime.rtc.TrackPublishOptions",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        "media_service.app.livekit_runtime.rtc.TrackSource",
        SimpleNamespace(SOURCE_MICROPHONE="microphone"),
    )
    runtime = LiveKitRoomRuntime(_settings())

    with pytest.raises(RuntimeError, match="publish failed"):
        await runtime.connect_proxy(
            "session-1", "runtime-1", 5, "study1-session-1-audio"
        )

    assert rooms[0].disconnect_count == 1
    assert "session-1" not in runtime._proxy_rooms
    assert "session-1" not in runtime._sources

    should_fail = False
    await runtime.connect_proxy(
        "session-1", "runtime-1", 5, "study1-session-1-audio"
    )
    assert len(rooms) == 2
    assert runtime._proxy_rooms["session-1"] is rooms[1]
    assert "session-1" in runtime._sources
