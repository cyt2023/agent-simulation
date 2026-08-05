from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
import uuid

from .repository import MediaRepository
from .room_policy import (
    HandoffBarrier,
    RoomPolicySnapshot,
    SpeakingPolicy,
    stable_room_name,
)
from .schemas import RuntimeState


class LiveKitRuntime(Protocol):
    async def ensure_room(self, room_name: str) -> None: ...

    async def connect_proxy(
        self, session_id: str, runtime_id: str, phase_version: int, room_name: str
    ) -> None: ...

    async def connect_recorder(
        self, session_id: str, runtime_id: str, phase_version: int, room_name: str
    ) -> None: ...

    async def disconnect(self, session_id: str) -> None: ...

    async def disconnect_proxy(self, session_id: str) -> None: ...

    async def apply_speaking_policy(
        self, session_id: str, room_name: str, policy: SpeakingPolicy
    ) -> RoomPolicySnapshot: ...


class MediaLifecycle(Protocol):
    async def start_session(
        self,
        session_id: str,
        runtime_id: str,
        context: dict,
        *,
        proxy_enabled: bool,
        artifact_version: str,
    ) -> None: ...

    async def finalize(self, session_id: str, phase_version: int) -> None: ...

    async def cancel(self, session_id: str) -> None: ...

    async def regenerate_summary(
        self, session_id: str, phase_version: int, payload: dict
    ) -> None: ...

    async def purge_session_media(self, session_id: str, payload: dict) -> None: ...


def room_name(session_id: str, room_kind: str, phase_version: int) -> str:
    return stable_room_name(session_id)


class RuntimeCoordinator:
    def __init__(
        self,
        repository: MediaRepository,
        livekit: LiveKitRuntime,
        lifecycle: MediaLifecycle | None = None,
    ):
        self.repository = repository
        self.livekit = livekit
        self.lifecycle = lifecycle
        self._handoff_barriers: dict[str, HandoffBarrier] = {}

    async def reconcile(self) -> None:
        """Reattach persisted active runtimes after a B process restart."""
        runtimes = self.repository.nonterminal_runtimes()
        sync_sessions = {
            runtime.session_id
            for runtime in runtimes
            if runtime.room_kind == "sync"
        }
        for runtime in runtimes:
            if (
                runtime.room_kind == "proxy"
                and runtime.session_id in sync_sessions
            ):
                self.repository.update_runtime_state(
                    runtime.runtime_id, RuntimeState.STOPPED, ended=True
                )
                continue
            proxy_can_resume = (
                runtime.room_kind == "proxy"
                and runtime.state
                in (RuntimeState.PREPARING.value, RuntimeState.ACTIVE.value)
            )
            if self.lifecycle and (
                runtime.room_kind == "sync" or proxy_can_resume
            ):
                await self.lifecycle.start_session(
                    runtime.session_id,
                    runtime.runtime_id,
                    runtime.runtime_config if runtime.room_kind == "proxy" else {},
                    proxy_enabled=runtime.room_kind == "proxy",
                    artifact_version=(
                        "1"
                        if runtime.room_kind == "proxy"
                        else f"sync-{runtime.phase_version}"
                    ),
                )
            await self.livekit.ensure_room(runtime.room_name)
            if runtime.room_kind == "proxy":
                await self.livekit.connect_recorder(
                    runtime.session_id,
                    runtime.runtime_id,
                    runtime.phase_version,
                    runtime.room_name,
                )
                if proxy_can_resume:
                    await self.livekit.connect_proxy(
                        runtime.session_id,
                        runtime.runtime_id,
                        runtime.phase_version,
                        runtime.room_name,
                    )
                else:
                    handoff_version = (runtime.runtime_config or {}).get(
                        "handoff_phase_version"
                    )
                    if handoff_version:
                        self._handoff_barriers[runtime.session_id] = HandoffBarrier(
                            runtime.session_id,
                            int(handoff_version),
                            runtime.runtime_id,
                            principal_joined_at=(runtime.runtime_config or {}).get(
                                "principal_joined_at"
                            ),
                            proxy_stopped_at=(runtime.runtime_config or {}).get(
                                "proxy_stopped_at"
                            ),
                        )
                        await self._refresh_handoff(
                            runtime.session_id, runtime.room_name
                        )
                if proxy_can_resume:
                    runtime = self._mark_media_ready(runtime)
            else:
                await self.livekit.connect_recorder(
                    runtime.session_id,
                    runtime.runtime_id,
                    runtime.phase_version,
                    runtime.room_name,
                )
                await self.livekit.apply_speaking_policy(
                    runtime.session_id,
                    runtime.room_name,
                    SpeakingPolicy.SYNC,
                )
                if runtime.state in (
                    RuntimeState.PREPARING.value,
                    RuntimeState.ACTIVE.value,
                ):
                    runtime = self._mark_media_ready(runtime)

    def _mark_media_ready(self, runtime):
        return self.repository.transition_runtime_with_event(
            runtime.runtime_id,
            state=RuntimeState.ACTIVE,
            session_id=runtime.session_id,
            phase_version=runtime.phase_version,
            event_type="MEDIA_READY",
            payload={
                "room_kind": runtime.room_kind,
                "runtime_id": runtime.runtime_id,
            },
        )

    async def start_proxy(self, session_id: str, phase_version: int, config: dict):
        runtime, created = self.repository.get_or_create_runtime(
            runtime_id=str(uuid.uuid4()),
            session_id=session_id,
            phase_version=phase_version,
            room_kind="proxy",
            room_name=room_name(session_id, "proxy", phase_version),
            state=RuntimeState.PREPARING,
            runtime_config=config,
        )
        if not created and runtime.state == RuntimeState.ACTIVE.value:
            return self._mark_media_ready(runtime)
        if self.lifecycle:
            await self.lifecycle.start_session(
                session_id,
                runtime.runtime_id,
                config,
                proxy_enabled=True,
                artifact_version="1",
            )
        await self.livekit.ensure_room(runtime.room_name)
        await self.livekit.connect_recorder(
            session_id, runtime.runtime_id, phase_version, runtime.room_name
        )
        await self.livekit.connect_proxy(
            session_id, runtime.runtime_id, phase_version, runtime.room_name
        )
        return self._mark_media_ready(runtime)

    async def start_sync(self, session_id: str, phase_version: int):
        for previous in self.repository.list_session_runtimes(session_id):
            if previous.room_kind != "proxy" or previous.ended_at is not None:
                continue
            try:
                if (
                    self.lifecycle
                    and previous.state != RuntimeState.HANDING_OFF.value
                ):
                    await self.lifecycle.finalize(
                        session_id, previous.phase_version
                    )
            except Exception:
                self.repository.update_runtime_state(
                    previous.runtime_id, RuntimeState.ERROR, ended=True
                )
                await self.livekit.disconnect(session_id)
                raise
            await self.livekit.disconnect_proxy(session_id)
            self.repository.finish_runtime_with_event(
                previous.runtime_id,
                state=RuntimeState.STOPPED,
                session_id=session_id,
                phase_version=previous.phase_version,
                event_type="MEETING_ENDED",
                payload={
                    "room_kind": previous.room_kind,
                    "runtime_id": previous.runtime_id,
                },
            )
        self._handoff_barriers.pop(session_id, None)
        runtime, created = self.repository.get_or_create_runtime(
            runtime_id=str(uuid.uuid4()),
            session_id=session_id,
            phase_version=phase_version,
            room_kind="sync",
            room_name=room_name(session_id, "sync", phase_version),
            state=RuntimeState.PREPARING,
            runtime_config={"proxy_enabled": False},
        )
        if not created and runtime.state == RuntimeState.ACTIVE.value:
            return self._mark_media_ready(runtime)
        if self.lifecycle:
            await self.lifecycle.start_session(
                session_id,
                runtime.runtime_id,
                {},
                proxy_enabled=False,
                artifact_version=f"sync-{phase_version}",
            )
        await self.livekit.ensure_room(runtime.room_name)
        await self.livekit.connect_recorder(
            session_id, runtime.runtime_id, phase_version, runtime.room_name
        )
        await self.livekit.apply_speaking_policy(
            session_id, runtime.room_name, SpeakingPolicy.SYNC
        )
        return self._mark_media_ready(runtime)

    async def end_current(self, session_id: str, phase_version: int) -> None:
        runtime = self.repository.active_runtime(session_id)
        if not runtime or runtime.ended_at is not None:
            return
        if (
            runtime.room_kind == "proxy"
            and runtime.state == RuntimeState.HANDING_OFF.value
        ):
            if runtime.phase_version == phase_version:
                return
            raise RuntimeError(
                "Sync meeting is not active yet; retry END_CURRENT_MEETING after START_SYNC_MEETING"
            )
        self.repository.update_runtime_state(runtime.runtime_id, RuntimeState.ENDING)
        try:
            if self.lifecycle:
                await self.lifecycle.finalize(session_id, phase_version)
        except Exception:
            self.repository.update_runtime_state(
                runtime.runtime_id, RuntimeState.ERROR, ended=True
            )
            self._handoff_barriers.pop(session_id, None)
            await self.livekit.disconnect(session_id)
            raise
        proxy_stopped_at = None
        if runtime.room_kind == "proxy":
            await self.livekit.disconnect_proxy(session_id)
            proxy_stopped_at = (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        else:
            await self.livekit.disconnect(session_id)
        transition = (
            self.repository.transition_runtime_with_event
            if runtime.room_kind == "proxy"
            else self.repository.finish_runtime_with_event
        )
        transition(
            runtime.runtime_id,
            state=(
                RuntimeState.HANDING_OFF
                if runtime.room_kind == "proxy"
                else RuntimeState.STOPPED
            ),
            session_id=session_id,
            phase_version=phase_version,
            event_type="MEETING_ENDED",
            payload={
                "room_kind": runtime.room_kind,
                "runtime_id": runtime.runtime_id,
                **(
                    {"proxy_stopped_at": proxy_stopped_at}
                    if proxy_stopped_at
                    else {}
                ),
            },
            runtime_config_patch=(
                {"proxy_stopped_at": proxy_stopped_at}
                if proxy_stopped_at
                else None
            ),
        )

    async def begin_handoff(self, session_id: str, phase_version: int) -> None:
        required_roles = {"principal", "teammate_1", "teammate_2"}
        ready_roles = self.repository.preflight_ready_roles(session_id)
        if not required_roles <= ready_roles:
            missing = sorted(required_roles - ready_roles)
            self.repository.enqueue_event(
                session_id,
                phase_version,
                "MEDIA_ERROR",
                {
                    "error_code": "HANDOFF_MEDIA_NOT_READY",
                    "missing_roles": missing,
                    "readiness_source": "device_preflight",
                },
            )
            raise RuntimeError(
                "All P/T1/T2 participants must be media ready before handoff"
            )
        runtime = self.repository.active_runtime(session_id)
        if (
            runtime
            and runtime.room_kind == "proxy"
            and runtime.state != RuntimeState.HANDING_OFF.value
        ):
            if self.lifecycle:
                await self.lifecycle.cancel(session_id)
            await self.livekit.disconnect_proxy(session_id)
            runtime = self.repository.mark_runtime_handoff(
                runtime.runtime_id, phase_version
            )
        elif runtime and runtime.room_kind == "proxy":
            runtime = self.repository.mark_runtime_handoff(
                runtime.runtime_id, phase_version
            )
        stable_room = room_name(session_id, "sync", phase_version)
        await self.livekit.ensure_room(stable_room)
        self._handoff_barriers.setdefault(
            session_id,
            HandoffBarrier(
                session_id,
                phase_version,
                runtime.runtime_id if runtime and runtime.room_kind == "proxy" else None,
                principal_joined_at=(runtime.runtime_config or {}).get(
                    "principal_joined_at"
                )
                if runtime
                else None,
                proxy_stopped_at=(runtime.runtime_config or {}).get(
                    "proxy_stopped_at"
                )
                if runtime
                else None,
            ),
        )
        await self._refresh_handoff(session_id, stable_room)

    async def _refresh_handoff(self, session_id: str, stable_room: str) -> None:
        barrier = self._handoff_barriers.get(session_id)
        if not barrier:
            return
        snapshot = await self.livekit.apply_speaking_policy(
            session_id, stable_room, SpeakingPolicy.HANDOFF
        )
        complete = barrier.observe(snapshot)
        if barrier.runtime_id:
            self.repository.patch_runtime_config(
                barrier.runtime_id,
                {
                    "principal_joined_at": barrier.principal_joined_at,
                    "proxy_stopped_at": barrier.proxy_stopped_at,
                },
            )
        if not complete:
            return
        if barrier.runtime_id:
            self.repository.finish_runtime_with_event(
                barrier.runtime_id,
                state=RuntimeState.STOPPED,
                session_id=session_id,
                phase_version=barrier.phase_version,
                event_type="HANDOFF_COMPLETE",
                payload={
                    "runtime_id": barrier.runtime_id,
                    "proxy_disconnected": True,
                    "sync_room_ready": True,
                    "room_name": stable_room,
                    "connected_roles": sorted(snapshot.connected_roles),
                    "can_publish_by_role": snapshot.can_publish_by_role,
                    "principal_joined_at": barrier.principal_joined_at,
                    "proxy_stopped_at": barrier.proxy_stopped_at,
                },
            )
        self._handoff_barriers.pop(session_id, None)

    async def stop_session(self, session_id: str, phase_version: int) -> None:
        cleanup_error: Exception | None = None
        try:
            if self.lifecycle:
                await self.lifecycle.cancel(session_id)
        except Exception as error:
            cleanup_error = error
        try:
            await self.livekit.disconnect(session_id)
        except Exception as error:
            cleanup_error = cleanup_error or error
        finally:
            self._handoff_barriers.pop(session_id, None)
            self.repository.finish_session_runtimes(
                session_id, RuntimeState.STOPPED
            )
        if cleanup_error:
            raise cleanup_error

    async def regenerate_summary(
        self, session_id: str, phase_version: int, payload: dict
    ) -> None:
        if not self.lifecycle:
            return
        await self.lifecycle.regenerate_summary(session_id, phase_version, payload)

    async def purge_session_media(
        self, session_id: str, phase_version: int, payload: dict
    ) -> None:
        runtime = self.repository.active_runtime(session_id)
        if runtime:
            await self.stop_session(session_id, phase_version)
        if self.lifecycle and hasattr(self.lifecycle, "purge_session_media"):
            await self.lifecycle.purge_session_media(session_id, payload)
        self.repository.purge_session_media(
            session_id,
            retention_job_id=str(payload.get("retention_job_id") or ""),
            manifest_checksum=str(payload.get("manifest_checksum") or ""),
            reason=str(payload.get("reason") or "Retention purge"),
            phase_version=phase_version,
        )

    async def participant_state_changed(
        self,
        session_id: str,
        participant_id: str,
        role: str,
        state: str,
        metadata: dict,
    ) -> None:
        runtime = self.repository.active_runtime(session_id)
        if not runtime:
            return
        self.repository.record_connection(
            session_id=session_id,
            runtime_id=runtime.runtime_id,
            participant_id=participant_id,
            role=role,
            state=state,
            device_metadata=metadata,
        )
        barrier = self._handoff_barriers.get(session_id)
        self.repository.enqueue_event(
            session_id,
            barrier.phase_version if barrier else runtime.phase_version,
            "PARTICIPANT_JOINED" if state == "connected" else "PARTICIPANT_LEFT",
            {
                "participant_id": participant_id,
                "role": role,
                "state": state,
                **metadata,
            },
        )
        if session_id in self._handoff_barriers:
            await self._refresh_handoff(
                session_id, room_name(session_id, "sync", runtime.phase_version)
            )
