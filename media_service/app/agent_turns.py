from __future__ import annotations

from typing import Any

from .repository import MediaRepository


class AgentTurnLedger:
    def __init__(self, repository: MediaRepository):
        self.repository = repository

    def begin(
        self,
        *,
        turn_id: str,
        session_id: str,
        runtime_id: str,
        phase_version: int,
        turn_kind: str,
        context_event_ids: list[str],
        authorized_snapshot: dict[str, Any],
    ):
        return self.repository.begin_agent_turn(
            {
                "turn_id": turn_id,
                "session_id": session_id,
                "runtime_id": runtime_id,
                "phase_version": phase_version,
                "turn_kind": turn_kind,
                "context_event_ids": context_event_ids,
                "authorized_snapshot": authorized_snapshot,
            }
        )

    def finish(self, turn_id: str, *, status: str, error_code: str | None = None):
        return self.repository.finish_agent_turn(
            turn_id,
            status=status,
            error_code=error_code,
        )
