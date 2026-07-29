from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
from contextlib import suppress
import io
from pathlib import Path
import re

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.responses import FileResponse

from .access import AccessDenied, MediaAccessService
from .audio_router import AudioPipelineRouter
from .auth import require_a_service
from .callbacks import CallbackClient
from .commands import CommandService
from .config import Settings
from .db import Database
from .export import build_media_export
from .livekit_runtime import LiveKitRoomRuntime
from .pipeline import ProxyMediaPipeline
from .providers.factory import create_providers
from .repository import MediaRepository
from .runtime import RuntimeCoordinator
from .schemas import (
    CommandAcceptance,
    CommandEnvelope,
    DeviceStatusRequest,
    MediaAccessRequest,
    MediaAccessResponse,
)


def create_app(
    settings: Settings | None = None,
    *,
    initialize_database: bool = True,
    runtime_coordinator=None,
) -> FastAPI:
    resolved_settings = settings or Settings()
    database = Database(resolved_settings)
    if initialize_database:
        database.create_all()
    repository = MediaRepository(database)
    if runtime_coordinator is None:
        livekit_runtime = LiveKitRoomRuntime(resolved_settings)
        providers = create_providers(resolved_settings)
        pipeline = ProxyMediaPipeline(
            repository,
            providers.asr,
            providers.llm,
            providers.tts,
            publish_audio=livekit_runtime.publish_audio,
            media_root=resolved_settings.media_root,
            proxy_prompt_version=resolved_settings.proxy_prompt_version,
            summary_prompt_version=resolved_settings.summary_prompt_version,
        )
        audio_router = AudioPipelineRouter(
            pipeline,
            resolved_settings.media_root,
            publish_audio=livekit_runtime.publish_audio,
        )
        pipeline.publish_audio = audio_router.publish_proxy_audio
        livekit_runtime.audio_consumer = audio_router.handle_frame
        resolved_runtime = RuntimeCoordinator(
            repository, livekit_runtime, lifecycle=audio_router
        )
        livekit_runtime.connection_consumer = (
            resolved_runtime.participant_state_changed
        )
    else:
        resolved_runtime = runtime_coordinator
    callback_client = CallbackClient(
        repository,
        resolved_settings.a_base_url,
        resolved_settings.study1_internal_api_key,
        timeout=resolved_settings.callback_timeout_seconds,
    )

    async def deliver_outbox_forever() -> None:
        while True:
            await callback_client.drain()
            await asyncio.sleep(resolved_settings.callback_poll_seconds)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if not initialize_database:
            database.create_all()
        if hasattr(resolved_runtime, "reconcile"):
            await resolved_runtime.reconcile()
        await app.state.command_service.reconcile_pending()
        callback_task = asyncio.create_task(deliver_outbox_forever())
        try:
            yield
        finally:
            callback_task.cancel()
            with suppress(asyncio.CancelledError):
                await callback_task

    app = FastAPI(
        title="Study 1 Media Service", version="0.1.0", lifespan=lifespan
    )
    app.state.settings = resolved_settings
    app.state.database = database
    app.state.repository = repository
    app.state.runtime_coordinator = resolved_runtime
    app.state.command_service = CommandService(repository, resolved_runtime)
    app.state.access_service = MediaAccessService(resolved_settings)
    app.state.callback_client = callback_client

    async def dispatch_with_error_event(command_id: str) -> None:
        row = repository.get_command(command_id)
        envelope = CommandEnvelope.model_validate(row.envelope)
        try:
            await app.state.command_service.execute(command_id)
        except Exception as error:
            repository.enqueue_event(
                envelope.session_id,
                envelope.phase_version,
                "MEDIA_ERROR",
                {
                    "command_id": envelope.command_id,
                    "command": envelope.command.value,
                    "error_type": type(error).__name__,
                    "message": str(error),
                },
            )

    @app.get("/healthz")
    def healthz():
        return {
            "service": "study1-media",
            "status": "ok",
            "schema": resolved_settings.media_database_schema,
        }

    @app.post(
        "/internal/commands",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=CommandAcceptance,
        dependencies=[Depends(require_a_service)],
    )
    def accept_command(envelope: CommandEnvelope, background_tasks: BackgroundTasks):
        try:
            result = app.state.command_service.accept(envelope)
            background_tasks.add_task(
                dispatch_with_error_event, result.command_id
            )
            return result
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post(
        "/internal/media-access",
        response_model=MediaAccessResponse,
        dependencies=[Depends(require_a_service)],
    )
    def media_access(payload: MediaAccessRequest):
        try:
            return app.state.access_service.issue_access(
                payload.session_id,
                payload.phase,
                payload.phase_version,
                payload.role,
                payload.participant_id,
            )
        except AccessDenied as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    @app.post(
        "/internal/device-status",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_a_service)],
    )
    def device_status(payload: DeviceStatusRequest):
        row = repository.record_connection(
            session_id=payload.session_id,
            runtime_id=f"preflight:{payload.session_id}:v{payload.phase_version}",
            participant_id=payload.participant_id,
            role=payload.role,
            state=payload.state,
            device_metadata=payload.device,
        )
        return {"accepted": True, "connection_id": row.connection_id}

    @app.get(
        "/internal/sessions/{session_id}/status",
        dependencies=[Depends(require_a_service)],
    )
    def media_status(session_id: str):
        runtimes = repository.list_session_runtimes(session_id)
        connections = repository.list_session_connections(session_id)
        artifacts = repository.list_session_artifacts(session_id)
        active = next(
            (runtime for runtime in reversed(runtimes) if runtime.ended_at is None),
            None,
        )
        latest_connections = {
            row.participant_id: row for row in connections
        }
        return {
            "session_id": session_id,
            "service_status": "ok",
            "mode": "mock" if resolved_settings.media_provider == "mock" else "live",
            "runtime_state": active.state if active else "IDLE",
            "room_kind": active.room_kind if active else None,
            "room_name": active.room_name if active else None,
            "connections": [
                {
                    "participant_id": row.participant_id,
                    "role": row.role,
                    "state": row.state,
                    "device": row.device_metadata,
                }
                for row in latest_connections.values()
            ],
            "asr": {"provider": resolved_settings.media_provider, "status": "ready"},
            "proxy": {
                "active": bool(active and active.room_kind == "proxy"),
                "prompt_version": resolved_settings.proxy_prompt_version,
            },
            "recording": {"status": "active" if active else "idle"},
            "artifacts": [
                {"type": row.kind, "version": row.version, "checksum": row.checksum}
                for row in artifacts
            ],
            "transcript_checksum": next(
                (row.checksum for row in reversed(artifacts) if row.kind == "transcript"),
                None,
            ),
            "summary_version": next(
                (row.version for row in reversed(artifacts) if row.kind == "summary"),
                None,
            ),
            "pending_callback_count": len(
                [
                    row
                    for row in repository.list_session_outbox(session_id)
                    if row.delivered_at is None
                ]
            ),
        }

    @app.get(
        "/internal/sessions/{session_id}/export",
        dependencies=[Depends(require_a_service)],
    )
    def media_export(session_id: str):
        payload = build_media_export(
            repository, session_id, media_root=resolved_settings.media_root
        )
        return StreamingResponse(
            io.BytesIO(payload),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{session_id}-media.zip"'
            },
        )

    @app.get(
        "/internal/sessions/{session_id}/recordings/{recording_id}",
        dependencies=[Depends(require_a_service)],
    )
    def recording_replay(session_id: str, recording_id: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]+\.wav", recording_id):
            raise HTTPException(status_code=404, detail="Recording not found")
        session_root = (Path(resolved_settings.media_root) / session_id).resolve()
        target = (session_root / recording_id).resolve()
        if target.parent != session_root or not target.is_file():
            raise HTTPException(status_code=404, detail="Recording not found")
        return FileResponse(target, media_type="audio/wav", filename=recording_id)

    return app
