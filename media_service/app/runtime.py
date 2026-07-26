from __future__ import annotations

from typing import Protocol
import uuid

from .repository import MediaRepository
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


def room_name(session_id: str, room_kind: str, phase_version: int) -> str:
    safe_session = "".join(
        character if character.isalnum() or character in "_-" else "-"
        for character in session_id
    )[:96]
    return f"study1-{safe_session}-{room_kind}-v{phase_version}"


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

    async def reconcile(self) -> None:
        """Reattach persisted active runtimes after a B process restart."""
        for runtime in self.repository.nonterminal_runtimes():
            if self.lifecycle:
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
                await self.livekit.connect_proxy(
                    runtime.session_id,
                    runtime.runtime_id,
                    runtime.phase_version,
                    runtime.room_name,
                )
            else:
                await self.livekit.connect_recorder(
                    runtime.session_id,
                    runtime.runtime_id,
                    runtime.phase_version,
                    runtime.room_name,
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
            return runtime
        if self.lifecycle:
            await self.lifecycle.start_session(
                session_id,
                runtime.runtime_id,
                config,
                proxy_enabled=True,
                artifact_version="1",
            )
        await self.livekit.ensure_room(runtime.room_name)
        await self.livekit.connect_proxy(
            session_id, runtime.runtime_id, phase_version, runtime.room_name
        )
        runtime = self.repository.update_runtime_state(runtime.runtime_id, RuntimeState.ACTIVE)
        self.repository.enqueue_event(
            session_id,
            phase_version,
            "MEDIA_READY",
            {"room_kind": "proxy", "runtime_id": runtime.runtime_id},
        )
        return runtime

    async def start_sync(self, session_id: str, phase_version: int):
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
            return runtime
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
        runtime = self.repository.update_runtime_state(runtime.runtime_id, RuntimeState.ACTIVE)
        self.repository.enqueue_event(
            session_id,
            phase_version,
            "MEDIA_READY",
            {"room_kind": "sync", "runtime_id": runtime.runtime_id},
        )
        return runtime

    async def end_current(self, session_id: str, phase_version: int) -> None:
        runtime = self.repository.active_runtime(session_id)
        if not runtime or runtime.ended_at is not None:
            return
        self.repository.update_runtime_state(runtime.runtime_id, RuntimeState.ENDING)
        try:
            if self.lifecycle:
                await self.lifecycle.finalize(session_id, phase_version)
        except Exception:
            self.repository.update_runtime_state(
                runtime.runtime_id, RuntimeState.ERROR, ended=True
            )
            raise
        finally:
            await self.livekit.disconnect(session_id)
        self.repository.finish_runtime_with_event(
            runtime.runtime_id,
            state=RuntimeState.STOPPED,
            session_id=session_id,
            phase_version=phase_version,
            event_type="MEETING_ENDED",
            payload={
                "room_kind": runtime.room_kind,
                "runtime_id": runtime.runtime_id,
            },
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
        if runtime and runtime.room_kind == "proxy":
            if self.lifecycle:
                await self.lifecycle.cancel(session_id)
            await self.livekit.disconnect(session_id)
            self.repository.update_runtime_state(
                runtime.runtime_id, RuntimeState.STOPPED, ended=True
            )
        self.repository.enqueue_event(
            session_id,
            phase_version,
            "HANDOFF_COMPLETE",
            {"proxy_disconnected": True},
        )

    async def regenerate_summary(
        self, session_id: str, phase_version: int, payload: dict
    ) -> None:
        if not self.lifecycle:
            return
        await self.lifecycle.regenerate_summary(session_id, phase_version, payload)

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
        self.repository.enqueue_event(
            session_id,
            runtime.phase_version,
            "PARTICIPANT_JOINED" if state == "connected" else "PARTICIPANT_LEFT",
            {
                "participant_id": participant_id,
                "role": role,
                "state": state,
                **metadata,
            },
        )
