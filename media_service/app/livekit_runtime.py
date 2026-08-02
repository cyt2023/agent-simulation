from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from livekit import api, rtc

from .access import MediaAccessService
from .config import Settings
from .playback import PlaybackGeneration, ProxyPlaybackController
from .room_policy import (
    HANDOFF_HUMAN_ROLES,
    RoomPolicySnapshot,
    SpeakingPolicy,
)


AudioConsumer = Callable[[str, str, rtc.AudioFrame], Awaitable[None]]
ConnectionConsumer = Callable[
    [str, str, str, str, dict], Awaitable[None]
]


class LiveKitRoomRuntime:
    """LiveKit adapter used by the single server-side X participant."""

    def __init__(
        self,
        settings: Settings,
        audio_consumer: AudioConsumer | None = None,
        connection_consumer: ConnectionConsumer | None = None,
    ):
        self.settings = settings
        self.audio_consumer = audio_consumer
        self.connection_consumer = connection_consumer
        self._rooms: dict[str, rtc.Room] = {}
        self._recorder_rooms: dict[str, rtc.Room] = {}
        self._proxy_rooms: dict[str, rtc.Room] = {}
        self._sources: dict[str, rtc.AudioSource] = {}
        self._playbacks: dict[str, ProxyPlaybackController] = {}
        self._tasks: set[asyncio.Task] = set()
        self._connect_locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def ensure_room(self, room_name: str) -> None:
        http_url = self.settings.livekit_url.replace("ws://", "http://").replace(
            "wss://", "https://"
        )
        client = api.LiveKitAPI(
            http_url,
            self.settings.livekit_api_key,
            self.settings.livekit_api_secret,
        )
        try:
            existing = await client.room.list_rooms(
                api.ListRoomsRequest(names=[room_name])
            )
            if not existing.rooms:
                await client.room.create_room(api.CreateRoomRequest(name=room_name))
        finally:
            await client.aclose()

    async def connect_proxy(
        self, session_id: str, runtime_id: str, phase_version: int, room_name: str
    ) -> None:
        await self._connect(
            session_id,
            room_name,
            access=MediaAccessService(self.settings).issue_access(
                session_id,
                "PROXY_MEETING",
                phase_version,
                "proxy",
                f"proxy-{session_id}",
            ),
            publish_proxy=True,
            connection_kind="proxy",
            subscribe_audio=False,
        )

    async def connect_recorder(
        self, session_id: str, runtime_id: str, phase_version: int, room_name: str
    ) -> None:
        await self._connect(
            session_id,
            room_name,
            access=MediaAccessService(self.settings).issue_recorder_access(
                session_id, phase_version
            ),
            publish_proxy=False,
            connection_kind="recorder",
            subscribe_audio=True,
        )

    async def _connect(
        self,
        session_id: str,
        room_name: str,
        *,
        access,
        publish_proxy: bool,
        connection_kind: str,
        subscribe_audio: bool,
    ) -> None:
        rooms = (
            self._recorder_rooms
            if connection_kind == "recorder"
            else self._proxy_rooms
        )
        lock = self._connect_locks.setdefault(
            (connection_kind, session_id), asyncio.Lock()
        )
        async with lock:
            if session_id in rooms:
                return
            await self._connect_uncached(
                session_id,
                room_name,
                access=access,
                publish_proxy=publish_proxy,
                connection_kind=connection_kind,
                subscribe_audio=subscribe_audio,
                rooms=rooms,
            )

    async def _connect_uncached(
        self,
        session_id: str,
        room_name: str,
        *,
        access,
        publish_proxy: bool,
        connection_kind: str,
        subscribe_audio: bool,
        rooms: dict[str, rtc.Room],
    ) -> None:
        room = rtc.Room()

        @room.on("track_subscribed")
        def on_track_subscribed(track, _publication, participant):
            if (
                not subscribe_audio
                or track.kind != rtc.TrackKind.KIND_AUDIO
                or not self.audio_consumer
            ):
                return
            task = asyncio.create_task(
                self._consume_track(
                    session_id, participant.name or participant.identity, track
                )
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        @room.on("participant_connected")
        def on_participant_connected(participant):
            if not subscribe_audio:
                return
            self._schedule_connection(
                session_id, room_name, participant, "connected"
            )

        @room.on("participant_disconnected")
        def on_participant_disconnected(participant):
            if not subscribe_audio:
                return
            self._schedule_connection(
                session_id, room_name, participant, "disconnected"
            )

        @room.on("disconnected")
        def on_disconnected(_reason):
            if rooms.get(session_id) is room:
                rooms.pop(session_id, None)
            if connection_kind == "proxy":
                self._sources.pop(session_id, None)
                self._playbacks.pop(session_id, None)

        source = None
        try:
            await room.connect(
                self.settings.livekit_url,
                access.token,
                rtc.RoomOptions(auto_subscribe=subscribe_audio),
            )
            if subscribe_audio:
                for participant in room.remote_participants.values():
                    await self._emit_connection(
                        session_id, room_name, participant, "connected"
                    )
            if publish_proxy:
                source = rtc.AudioSource(24000, 1)
                track = rtc.LocalAudioTrack.create_audio_track("proxy", source)
                options = rtc.TrackPublishOptions(
                    source=rtc.TrackSource.SOURCE_MICROPHONE
                )
                await room.local_participant.publish_track(track, options)
            rooms[session_id] = room
            if source is not None:
                self._sources[session_id] = source
                self._playbacks[session_id] = ProxyPlaybackController(source)
        except BaseException:
            if rooms.get(session_id) is room:
                rooms.pop(session_id, None)
            self._sources.pop(session_id, None)
            self._playbacks.pop(session_id, None)
            try:
                await room.disconnect()
            except BaseException:
                pass
            raise

    def _schedule_connection(
        self, session_id: str, room_name: str, participant, state: str
    ) -> None:
        task = asyncio.create_task(
            self._emit_connection(
                session_id, room_name, participant, state
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _emit_connection(
        self, session_id: str, room_name: str, participant, state: str
    ) -> None:
        if not self.connection_consumer:
            return
        await self.connection_consumer(
            session_id,
            participant.identity,
            participant.name or participant.identity,
            state,
            {"room_name": room_name},
        )

    async def _consume_track(
        self, session_id: str, identity: str, track: rtc.Track
    ) -> None:
        assert self.audio_consumer is not None
        async for event in rtc.AudioStream(track, sample_rate=48000, num_channels=1):
            await self.audio_consumer(session_id, identity, event.frame)

    def _playback(self, session_id: str) -> ProxyPlaybackController:
        playback = self._playbacks.get(session_id)
        if playback:
            return playback
        source = self._sources[session_id]
        playback = ProxyPlaybackController(source)
        self._playbacks[session_id] = playback
        return playback

    def begin_proxy_audio(
        self, session_id: str, turn_id: str
    ) -> PlaybackGeneration:
        return self._playback(session_id).begin(turn_id, session_id=session_id)

    async def interrupt_proxy_audio(
        self,
        session_id: str,
        generation: PlaybackGeneration | None = None,
    ) -> bool:
        playback = self._playbacks.get(session_id)
        if not playback:
            return False
        return await playback.interrupt(generation, session_id=session_id)

    async def publish_audio(
        self,
        session_id: str,
        pcm_s16le: bytes,
        *,
        generation: PlaybackGeneration | None = None,
    ) -> bool:
        source = self._sources[session_id]
        frame = rtc.AudioFrame(
            data=pcm_s16le,
            sample_rate=24000,
            num_channels=1,
            samples_per_channel=len(pcm_s16le) // 2,
        )
        if generation is not None:
            return await self._playback(session_id).publish(generation, frame)
        await source.capture_frame(frame)
        return True

    async def apply_speaking_policy(
        self,
        session_id: str,
        room_name: str,
        policy: SpeakingPolicy,
    ) -> RoomPolicySnapshot:
        await self.disconnect_proxy(session_id)
        can_publish = policy is SpeakingPolicy.SYNC
        http_url = self.settings.livekit_url.replace("ws://", "http://").replace(
            "wss://", "https://"
        )
        client = api.LiveKitAPI(
            http_url,
            self.settings.livekit_api_key,
            self.settings.livekit_api_secret,
        )
        connected_roles: set[str] = set()
        can_publish_by_role: dict[str, bool] = {}
        try:
            response = await client.room.list_participants(
                api.ListParticipantsRequest(room=room_name)
            )
            for participant in response.participants:
                role = participant.name or participant.identity
                if role == "proxy":
                    await client.room.remove_participant(
                        api.RoomParticipantIdentity(
                            room=room_name, identity=participant.identity
                        )
                    )
                    continue
                if role not in HANDOFF_HUMAN_ROLES:
                    continue
                await client.room.update_participant(
                    api.UpdateParticipantRequest(
                        room=room_name,
                        identity=participant.identity,
                        permission=api.ParticipantPermission(
                            can_subscribe=True,
                            can_publish=can_publish,
                            can_publish_data=False,
                            can_publish_sources=(
                                [api.TrackSource.MICROPHONE]
                                if can_publish
                                else []
                            ),
                        ),
                    )
                )
                connected_roles.add(role)
                can_publish_by_role[role] = can_publish
        finally:
            await client.aclose()
        return RoomPolicySnapshot(
            connected_roles=frozenset(connected_roles),
            proxy_present=False,
            can_publish_by_role=can_publish_by_role,
        )

    async def disconnect(self, session_id: str) -> None:
        await self.disconnect_proxy(session_id)
        recorder = self._recorder_rooms.pop(session_id, None)
        legacy = self._rooms.pop(session_id, None)
        if recorder:
            await recorder.disconnect()
        if legacy and legacy is not recorder:
            await legacy.disconnect()

    async def disconnect_proxy(self, session_id: str) -> None:
        self._sources.pop(session_id, None)
        self._playbacks.pop(session_id, None)
        room = self._proxy_rooms.pop(session_id, None)
        if room:
            await room.disconnect()
