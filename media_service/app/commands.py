from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Protocol

from .repository import MediaRepository
from .schemas import CommandAcceptance, CommandEnvelope, MediaCommand, RuntimeState


_INITIAL_STATE = {
    MediaCommand.START_PROXY_MEETING: RuntimeState.PREPARING,
    MediaCommand.END_CURRENT_MEETING: RuntimeState.ENDING,
    MediaCommand.BEGIN_HANDOFF: RuntimeState.HANDING_OFF,
    MediaCommand.START_SYNC_MEETING: RuntimeState.PREPARING,
    MediaCommand.REGENERATE_SUMMARY: RuntimeState.PROCESSING,
    MediaCommand.STOP_SESSION: RuntimeState.STOPPED,
    MediaCommand.PURGE_SESSION_MEDIA: RuntimeState.PROCESSING,
}


def semantic_key(command: CommandEnvelope) -> str:
    if command.command is MediaCommand.START_PROXY_MEETING:
        context = command.payload.get("authorized_context")
        if (
            not isinstance(context, dict)
            or not isinstance(context.get("materials"), list)
            or not isinstance(context.get("proxy_config"), dict)
            or not str(context.get("authorization_submission_id") or "")
            or not str(context.get("proxy_config_submission_id") or "")
        ):
            raise ValueError(
                "START_PROXY_MEETING requires A-built authorized_context"
            )
    if command.command is MediaCommand.REGENERATE_SUMMARY:
        payload = command.payload
        checksum = str(payload.get("source_transcript_checksum") or "")
        version = str(payload.get("source_summary_version") or "")
        if not checksum or not version or not str(payload.get("reason") or "").strip():
            raise ValueError(
                "REGENERATE_SUMMARY requires reason, source_transcript_checksum, and source_summary_version"
            )
        return f"{command.session_id}:summary:{checksum}:{version}"
    if command.command is MediaCommand.PURGE_SESSION_MEDIA:
        payload = command.payload
        retention_job_id = str(payload.get("retention_job_id") or "")
        manifest_checksum = str(payload.get("manifest_checksum") or "")
        reason = str(payload.get("reason") or "").strip()
        if not retention_job_id or not manifest_checksum or not reason:
            raise ValueError(
                "PURGE_SESSION_MEDIA requires retention_job_id, manifest_checksum, and reason"
            )
        return f"{command.session_id}:purge:{retention_job_id}:{manifest_checksum}"
    return f"{command.session_id}:{command.phase_version}:{command.command.value}"


class RuntimeCommands(Protocol):
    async def start_proxy(self, session_id: str, phase_version: int, config: dict): ...
    async def start_sync(self, session_id: str, phase_version: int): ...
    async def begin_handoff(self, session_id: str, phase_version: int): ...
    async def end_current(self, session_id: str, phase_version: int): ...
    async def stop_session(self, session_id: str, phase_version: int): ...
    async def purge_session_media(
        self, session_id: str, phase_version: int, payload: dict
    ): ...
    async def regenerate_summary(
        self, session_id: str, phase_version: int, payload: dict
    ): ...


class CommandService:
    def __init__(
        self, repository: MediaRepository, runtime: RuntimeCommands | None = None
    ):
        self.repository = repository
        self.runtime = runtime
        self._session_locks: dict[str, asyncio.Lock] = {}

    def accept(self, envelope: CommandEnvelope) -> CommandAcceptance:
        result = self.repository.accept_command(
            envelope, semantic_key(envelope), _INITIAL_STATE[envelope.command]
        )
        return CommandAcceptance.model_validate(result.__dict__)

    async def execute(self, command_id: str) -> None:
        row = self.repository.get_command(command_id)
        if row.status == "completed":
            return
        envelope = CommandEnvelope.model_validate(row.envelope)
        lock = self._session_locks.setdefault(envelope.session_id, asyncio.Lock())
        async with lock:
            row = self.repository.get_command(command_id)
            if row.status == "completed" or not self.repository.claim_command(command_id):
                return
            try:
                await self.dispatch(envelope)
            except Exception as error:
                self.repository.mark_command_status(
                    command_id, "failed", error_code=type(error).__name__
                )
                raise
            self.repository.mark_command_status(command_id, "completed")

    async def reconcile_pending(self) -> None:
        self.repository.requeue_interrupted_commands()
        for row in self.repository.pending_commands():
            try:
                await self.execute(row.command_id)
            except Exception:
                # A rejected operational command (for example, handoff before
                # device readiness) must remain retryable without preventing the
                # media service from starting and processing other sessions.
                continue

    async def dispatch(self, envelope: CommandEnvelope) -> None:
        if not self.runtime:
            return
        if envelope.command is MediaCommand.START_PROXY_MEETING:
            context = envelope.payload.get("authorized_context")
            if not isinstance(context, dict):
                raise ValueError("START_PROXY_MEETING requires authorized_context")
            await self.runtime.start_proxy(
                envelope.session_id, envelope.phase_version, context
            )
        elif envelope.command is MediaCommand.START_SYNC_MEETING:
            await self.runtime.start_sync(envelope.session_id, envelope.phase_version)
        elif envelope.command is MediaCommand.BEGIN_HANDOFF:
            await self.runtime.begin_handoff(
                envelope.session_id, envelope.phase_version
            )
        elif envelope.command is MediaCommand.END_CURRENT_MEETING:
            await self.runtime.end_current(
                envelope.session_id, envelope.phase_version
            )
        elif envelope.command is MediaCommand.STOP_SESSION:
            await self.runtime.stop_session(
                envelope.session_id, envelope.phase_version
            )
        elif envelope.command is MediaCommand.PURGE_SESSION_MEDIA:
            await self.runtime.purge_session_media(
                envelope.session_id, envelope.phase_version, envelope.payload
            )
        elif envelope.command is MediaCommand.REGENERATE_SUMMARY:
            await self.runtime.regenerate_summary(
                envelope.session_id, envelope.phase_version, envelope.payload
            )
