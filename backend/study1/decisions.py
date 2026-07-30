"""Normalized individual decision validation for formal Study 1 Sessions."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping

from .models import Study1Phase, Study1Role


class DecisionKind(StrEnum):
    PRE_INDIVIDUAL = "pre_individual"
    TENTATIVE_INDIVIDUAL = "tentative_individual"
    TEAM_FINAL = "team_final"
    FINAL_INDIVIDUAL = "final_individual"


class DecisionValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


DECISION_POLICY = {
    DecisionKind.PRE_INDIVIDUAL: (
        Study1Phase.PRE_VOTE.value,
        {"principal", "teammate_1", "teammate_2"},
    ),
    DecisionKind.TENTATIVE_INDIVIDUAL: (
        Study1Phase.TENTATIVE_DECISION.value,
        {"teammate_1", "teammate_2"},
    ),
    DecisionKind.FINAL_INDIVIDUAL: (
        Study1Phase.FINAL_DECISION.value,
        {"principal", "teammate_1", "teammate_2"},
    ),
}


def validate_individual_decision(
    kind: DecisionKind | str,
    session: Mapping[str, Any],
    identity: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        decision_kind = DecisionKind(kind)
    except ValueError as error:
        raise DecisionValidationError("INVALID_DECISION_KIND", "Unknown decision kind") from error
    if decision_kind is DecisionKind.TEAM_FINAL:
        raise DecisionValidationError(
            "SHARED_DECISION_REQUIRED", "team_final must use the shared artifact workflow"
        )
    required_phase, roles = DECISION_POLICY[decision_kind]
    if session.get("phase") != required_phase:
        raise DecisionValidationError(
            "ACTION_NOT_ALLOWED_IN_PHASE",
            f"{decision_kind.value} requires {required_phase}",
        )
    role = str(identity.get("role") or "")
    if role not in roles:
        raise DecisionValidationError("FORBIDDEN", "Role cannot submit this decision")
    candidate_ids = {
        str(value)
        for value in (session.get("candidate_ids") or [])
        if str(value)
    }
    candidate_id = str(payload.get("candidate_id") or "").strip()
    if candidate_id not in candidate_ids:
        raise DecisionValidationError(
            "INVALID_CANDIDATE_ID", "candidate_id must reference the registered task"
        )
    rationale = str(payload.get("rationale") or "").strip()
    if not rationale:
        raise DecisionValidationError("RATIONALE_REQUIRED", "rationale is required")
    confidence = payload.get("confidence")
    if confidence is not None:
        try:
            confidence = int(confidence)
        except (TypeError, ValueError) as error:
            raise DecisionValidationError("INVALID_CONFIDENCE", "confidence must be 1 to 7") from error
        if confidence < 1 or confidence > 7:
            raise DecisionValidationError("INVALID_CONFIDENCE", "confidence must be 1 to 7")
    return {
        "decision_kind": decision_kind.value,
        "candidate_id": candidate_id,
        "rationale": rationale,
        "confidence": confidence,
        "ratings": dict(payload.get("ratings") or {}),
        "decision_status": (
            str(payload.get("decision_status") or "").strip() or None
        ),
        "phase": required_phase,
    }
