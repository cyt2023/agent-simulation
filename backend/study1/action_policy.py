"""Canonical authorization policy for Study 1 actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .models import Study1Phase, Study1Role


class ActionPolicyViolation(ValueError):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ActionPolicy:
    statuses: frozenset[str]
    phases: frozenset[str] | None = None
    roles: frozenset[str] | None = None


HUMAN_ROLE_VALUES = frozenset(
    {
        Study1Role.PRINCIPAL.value,
        Study1Role.TEAMMATE_1.value,
        Study1Role.TEAMMATE_2.value,
    }
)

MATERIAL_PHASES_BY_ROLE = {
    Study1Role.PRINCIPAL.value: frozenset(
        {
            Study1Phase.MATERIAL_READING.value,
            Study1Phase.PROXY_CONFIGURATION.value,
            Study1Phase.HANDOFF.value,
            Study1Phase.SYNC_MEETING.value,
            Study1Phase.FINAL_DECISION.value,
            Study1Phase.FOLLOWUP_TASK.value,
        }
    ),
    Study1Role.TEAMMATE_1.value: frozenset(
        {
            Study1Phase.MATERIAL_READING.value,
            Study1Phase.HANDOFF.value,
            Study1Phase.SYNC_MEETING.value,
            Study1Phase.FINAL_DECISION.value,
            Study1Phase.FOLLOWUP_TASK.value,
        }
    ),
    Study1Role.TEAMMATE_2.value: frozenset(
        {
            Study1Phase.MATERIAL_READING.value,
            Study1Phase.HANDOFF.value,
            Study1Phase.SYNC_MEETING.value,
            Study1Phase.FINAL_DECISION.value,
            Study1Phase.FOLLOWUP_TASK.value,
        }
    ),
}

ACTION_POLICIES = {
    "submit": ActionPolicy(frozenset({"running"}), roles=HUMAN_ROLE_VALUES),
    "advance": ActionPolicy(frozenset({"running"}), roles=frozenset({"researcher"})),
    "issue_media_access": ActionPolicy(
        frozenset({"running"}), roles=HUMAN_ROLE_VALUES
    ),
    "issue_media_command": ActionPolicy(
        frozenset({"running"}), roles=frozenset({"researcher"})
    ),
    "material_write": ActionPolicy(
        frozenset({"waiting"}),
        phases=frozenset({Study1Phase.SETUP.value}),
        roles=frozenset({"researcher"}),
    ),
}


def authorize_action(
    session: Mapping[str, Any], action: str, role: str | None = None
) -> None:
    status = str(session.get("status") or "")
    if status == "paused":
        raise ActionPolicyViolation("SESSION_PAUSED", "Session is paused")
    if status in {"terminated", "completed"}:
        raise ActionPolicyViolation("SESSION_NOT_ACTIVE", "Session is not active")
    if action == "material_read":
        allowed = MATERIAL_PHASES_BY_ROLE.get(str(role), frozenset())
        if session.get("phase") not in allowed:
            raise ActionPolicyViolation(
                "MATERIAL_ACCESS_NOT_AVAILABLE",
                "Private materials are not available in the current phase",
                403,
            )
        return
    policy = ACTION_POLICIES.get(action)
    if policy is None:
        raise ActionPolicyViolation("UNKNOWN_ACTION", "Unknown Study 1 action", 400)
    if status not in policy.statuses:
        raise ActionPolicyViolation("ACTION_NOT_AVAILABLE", "Action is not available")
    if policy.phases is not None and session.get("phase") not in policy.phases:
        raise ActionPolicyViolation("ACTION_NOT_AVAILABLE", "Action is not available")
    if policy.roles is not None and str(role) not in policy.roles:
        raise ActionPolicyViolation("FORBIDDEN", "Role is not allowed for this action", 403)


def capabilities_for(session: Mapping[str, Any], role: str) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for action in (
        "submit",
        "advance",
        "issue_media_access",
        "issue_media_command",
        "material_read",
    ):
        try:
            authorize_action(session, action, role)
            result[action] = True
        except ActionPolicyViolation:
            result[action] = False
    return result
