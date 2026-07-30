from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import re


def safe_session_part(session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "-", session_id)[:96]


def stable_room_name(session_id: str) -> str:
    return f"study1-{safe_session_part(session_id)}-audio"


HANDOFF_HUMAN_ROLES = frozenset({"principal", "teammate_1", "teammate_2"})


class SpeakingPolicy(StrEnum):
    HANDOFF = "handoff"
    SYNC = "sync"


@dataclass(frozen=True)
class RoomPolicySnapshot:
    connected_roles: frozenset[str]
    proxy_present: bool
    can_publish_by_role: dict[str, bool]


@dataclass
class HandoffBarrier:
    session_id: str
    phase_version: int
    runtime_id: str | None = None
    last_snapshot: RoomPolicySnapshot | None = None
    principal_joined_at: str | None = None
    proxy_stopped_at: str | None = None

    def observe(self, snapshot: RoomPolicySnapshot) -> bool:
        self.last_snapshot = snapshot
        if "principal" in snapshot.connected_roles and not self.principal_joined_at:
            self.principal_joined_at = (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        humans_connected = HANDOFF_HUMAN_ROLES <= snapshot.connected_roles
        humans_muted = all(
            snapshot.can_publish_by_role.get(role) is False
            for role in HANDOFF_HUMAN_ROLES
        )
        return humans_connected and not snapshot.proxy_present and humans_muted
