from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from livekit import api, rtc

from .access import MediaAccessService
from .config import Settings


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
        self._sources: dict[str, rtc.AudioSource] = {}
        self._tasks: set[asyncio.Task] = set()

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
        )

    async def _connect(self, session_id: str, room_name: str, *, access, publish_proxy: bool) -> None:
        if session_id in self._rooms:
            return
        room = rtc.Room()

        @room.on("track_subscribed")
        def on_track_subscribed(track, _publication, participant):
            if track.kind != rtc.TrackKind.KIND_AUDIO or not self.audio_consumer:
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
            self._schedule_connection(
                session_id, room_name, participant, "connected"
            )

        @room.on("participant_disconnected")
        def on_participant_disconnected(participant):
            self._schedule_connection(
                session_id, room_name, participant, "disconnected"
            )

        await room.connect(
            self.settings.livekit_url,
            access.token,
            rtc.RoomOptions(auto_subscribe=True),
        )
        for participant in room.remote_participants.values():
            await self._emit_connection(
                session_id, room_name, participant, "connected"
            )
        self._rooms[session_id] = room
        if publish_proxy:
            source = rtc.AudioSource(24000, 1)
            track = rtc.LocalAudioTrack.create_audio_track("proxy", source)
            options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            await room.local_participant.publish_track(track, options)
            self._sources[session_id] = source

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

    async def publish_audio(self, session_id: str, pcm_s16le: bytes) -> None:
        source = self._sources[session_id]
        frame = rtc.AudioFrame(
            data=pcm_s16le,
            sample_rate=24000,
            num_channels=1,
            samples_per_channel=len(pcm_s16le) // 2,
        )
        await source.capture_frame(frame)

    async def disconnect(self, session_id: str) -> None:
        room = self._rooms.pop(session_id, None)
        self._sources.pop(session_id, None)
        if room:
            await room.disconnect()
