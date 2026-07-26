"""The only Study 1 phase transition implementation.

Routes and services may calculate readiness, but they must call
``transition_phase`` to change a phase.  The function is storage-neutral so it
can be tested without PostgreSQL; the service persists the returned append-only
transition record in the same transaction as the session snapshot update.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping

from .models import HUMAN_ROLES, PHASE_ORDER, Study1Phase


class TransitionError(ValueError):
    """Base class for rejected state transitions."""


class InvalidTransition(TransitionError):
    pass


class PrerequisitesNotMet(TransitionError):
    def __init__(self, missing: tuple[str, ...]):
        super().__init__("Missing prerequisites: " + ", ".join(missing))
        self.missing = missing


class OverrideReasonRequired(TransitionError):
    pass


@dataclass(frozen=True)
class TransitionCheck:
    allowed: bool
    current_phase: Study1Phase
    target_phase: Study1Phase
    missing: tuple[str, ...] = ()
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.allowed


def _utc_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_true(completion: Mapping[str, Any], key: str) -> bool:
    return completion.get(key) is True


def _all_roles(completion: Mapping[str, Any], prefix: str) -> list[str]:
    return [
        f"{prefix}:{role.value}"
        for role in HUMAN_ROLES
        if not _is_true(completion, f"{prefix}:{role.value}")
    ]


def missing_prerequisites(
    session: Mapping[str, Any], target_phase: Study1Phase | str
) -> tuple[str, ...]:
    """Return canonical prerequisite keys missing for the requested target."""

    target = Study1Phase(target_phase)
    completion = session.get("completion") or {}
    missing: list[str] = []

    if target is Study1Phase.PRE_VOTE:
        missing.extend(_all_roles(completion, "material_ack"))
    elif target is Study1Phase.PROXY_CONFIGURATION:
        missing.extend(_all_roles(completion, "pre_vote"))
    elif target is Study1Phase.PROXY_MEETING:
        for key in (
            "proxy_config:principal",
            "proxy_ready:teammate_1",
            "proxy_ready:teammate_2",
        ):
            if not _is_true(completion, key):
                missing.append(key)
    elif target is Study1Phase.TENTATIVE_DECISION:
        if not _is_true(completion, "proxy_meeting_ended"):
            missing.append("proxy_meeting_ended")
    elif target is Study1Phase.DELEGATION_EXPECTATION:
        for role in ("teammate_1", "teammate_2"):
            key = f"tentative_decision:{role}"
            if not _is_true(completion, key):
                missing.append(key)
    elif target is Study1Phase.REVIEW:
        for key in ("delegation_expectation:principal", "summary_artifact_ready"):
            if not _is_true(completion, key):
                missing.append(key)
    elif target is Study1Phase.COMPREHENSION_MEASUREMENT:
        for key in ("review_opened:principal", "review_reading_recorded:principal"):
            if not _is_true(completion, key):
                missing.append(key)
        if session.get("minimum_review_seconds") not in (None, 0):
            if not _is_true(completion, "minimum_review_time_met:principal"):
                missing.append("minimum_review_time_met:principal")
    elif target is Study1Phase.HANDOFF:
        if not _is_true(completion, "comprehension_measurement:principal"):
            missing.append("comprehension_measurement:principal")
    elif target is Study1Phase.SYNC_MEETING:
        if not _is_true(completion, "handoff_complete"):
            missing.append("handoff_complete")
    elif target is Study1Phase.FINAL_DECISION:
        if not _is_true(completion, "sync_meeting_ended"):
            missing.append("sync_meeting_ended")
    elif target is Study1Phase.FOLLOWUP_TASK:
        missing.extend(_all_roles(completion, "final_decision"))
    elif target is Study1Phase.POST_SURVEY:
        missing.extend(_all_roles(completion, "followup_task"))
    elif target is Study1Phase.COMPLETED:
        missing.extend(_all_roles(completion, "post_survey"))

    return tuple(missing)


def can_transition(
    session: Mapping[str, Any], target_phase: Study1Phase | str
) -> TransitionCheck:
    current = Study1Phase(session.get("phase", Study1Phase.SETUP))
    target = Study1Phase(target_phase)
    current_index = PHASE_ORDER.index(current)
    expected_index = current_index + 1

    if expected_index >= len(PHASE_ORDER) or PHASE_ORDER[expected_index] is not target:
        return TransitionCheck(
            False,
            current,
            target,
            reason="target_must_be_the_next_phase",
        )

    missing = missing_prerequisites(session, target)
    return TransitionCheck(not missing, current, target, missing=missing)


def readiness(session: Mapping[str, Any]) -> dict[str, Any]:
    """Compute the next phase and readiness without changing state."""

    current = Study1Phase(session.get("phase", Study1Phase.SETUP))
    index = PHASE_ORDER.index(current)
    if index + 1 >= len(PHASE_ORDER):
        return {
            "ready_to_advance": False,
            "next_phase": None,
            "missing_prerequisites": [],
        }
    target = PHASE_ORDER[index + 1]
    check = can_transition(session, target)
    return {
        "ready_to_advance": check.allowed,
        "next_phase": target.value,
        "missing_prerequisites": list(check.missing),
    }


def transition_phase(
    session: MutableMapping[str, Any],
    target_phase: Study1Phase | str,
    actor: Mapping[str, Any],
    reason: str | None = None,
    override: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Mutate ``session`` through one audited transition and return its event.

    The caller must persist both the snapshot and returned event atomically.
    ``actor`` is derived from server authentication, never request role fields.
    """

    target = Study1Phase(target_phase)
    check = can_transition(session, target)
    clean_reason = (reason or "").strip()

    if override and not clean_reason:
        raise OverrideReasonRequired("Force Advance requires a non-empty reason")
    if not override:
        if check.reason:
            raise InvalidTransition(check.reason)
        if check.missing:
            raise PrerequisitesNotMet(check.missing)

    timestamp = _utc_iso(now)
    current = Study1Phase(session.get("phase", Study1Phase.SETUP))
    prior_version = int(session.get("phase_version") or 1)
    actor_payload = {
        "participant_id": actor.get("participant_id"),
        "role": actor.get("role"),
    }
    event = {
        "event_type": "phase_transition",
        "from_phase": current.value,
        "to_phase": target.value,
        "from_phase_version": prior_version,
        "phase_version": prior_version + 1,
        "occurred_at": timestamp,
        "entered_by": actor_payload,
        "transition_reason": clean_reason or None,
        "override": bool(override),
        "prerequisites": {
            "satisfied": not check.missing,
            "missing": list(check.missing),
        },
    }

    history = session.setdefault("phase_history", [])
    if history:
        history[-1]["phase_ended_at"] = timestamp
    history.append(
        {
            "phase": target.value,
            "phase_version": prior_version + 1,
            "phase_started_at": timestamp,
            "phase_ended_at": None,
            "entered_by": copy.deepcopy(actor_payload),
            "transition_reason": clean_reason or None,
            "prerequisites": copy.deepcopy(event["prerequisites"]),
            "completion": copy.deepcopy(session.get("completion") or {}),
        }
    )
    session["phase"] = target.value
    session["phase_version"] = prior_version + 1
    session["phase_started_at"] = timestamp
    session["phase_ended_at"] = None
    session["entered_by"] = actor_payload
    session["transition_reason"] = clean_reason or None
    session["prerequisites"] = copy.deepcopy(event["prerequisites"])
    return event
