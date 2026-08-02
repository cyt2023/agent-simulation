"""Validation rules for formal Study 1 shared team artifacts."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Mapping

from .models import Study1Phase


class SharedArtifactKind(StrEnum):
    TEAM_FINAL = "team_final"
    FOLLOWUP_TASK = "followup_task"


class SharedArtifactValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


SHARED_ARTIFACT_PHASES = {
    SharedArtifactKind.TEAM_FINAL: Study1Phase.FINAL_DECISION.value,
    SharedArtifactKind.FOLLOWUP_TASK: Study1Phase.FOLLOWUP_TASK.value,
}


def validate_shared_artifact_context(
    kind: SharedArtifactKind | str,
    session: Mapping[str, Any],
    identity: Mapping[str, Any],
) -> SharedArtifactKind:
    try:
        artifact_kind = SharedArtifactKind(kind)
    except ValueError as error:
        raise SharedArtifactValidationError(
            "INVALID_SHARED_ARTIFACT_KIND", "Unknown shared artifact kind"
        ) from error
    required_phase = SHARED_ARTIFACT_PHASES[artifact_kind]
    if session.get("phase") != required_phase:
        raise SharedArtifactValidationError(
            "ACTION_NOT_ALLOWED_IN_PHASE",
            f"{artifact_kind.value} requires {required_phase}",
        )
    assigned = {
        (str(item.get("participant_id") or ""), str(item.get("role") or ""))
        for item in (session.get("participants") or [])
    }
    actor = (
        str(identity.get("participant_id") or ""),
        str(identity.get("role") or ""),
    )
    if actor not in assigned:
        raise SharedArtifactValidationError(
            "FORBIDDEN", "Participant is not assigned to this Session"
        )
    return artifact_kind


def validate_shared_content(
    kind: SharedArtifactKind | str,
    session: Mapping[str, Any],
    content: Mapping[str, Any],
) -> dict[str, Any]:
    artifact_kind = SharedArtifactKind(kind)
    if not isinstance(content, Mapping):
        raise SharedArtifactValidationError(
            "INVALID_SHARED_CONTENT", "Shared artifact content must be an object"
        )
    if artifact_kind is SharedArtifactKind.TEAM_FINAL:
        return _validate_team_final(session, content)
    return _validate_followup(content)


def content_checksum(content: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_team_final(
    session: Mapping[str, Any], content: Mapping[str, Any]
) -> dict[str, Any]:
    candidate_ids = {str(value) for value in session.get("candidate_ids") or []}
    candidate_id = str(content.get("candidate_id") or "").strip()
    if candidate_id not in candidate_ids:
        raise SharedArtifactValidationError(
            "INVALID_CANDIDATE_ID",
            "candidate_id must reference the registered task",
        )
    rationale = str(content.get("rationale") or "").strip()
    if not rationale:
        raise SharedArtifactValidationError(
            "RATIONALE_REQUIRED", "rationale is required"
        )
    confidence = content.get("confidence")
    if confidence is not None:
        if isinstance(confidence, bool):
            raise SharedArtifactValidationError(
                "INVALID_CONFIDENCE", "confidence must be 1 to 7"
            )
        try:
            confidence = int(confidence)
        except (TypeError, ValueError) as error:
            raise SharedArtifactValidationError(
                "INVALID_CONFIDENCE", "confidence must be 1 to 7"
            ) from error
        if not 1 <= confidence <= 7:
            raise SharedArtifactValidationError(
                "INVALID_CONFIDENCE", "confidence must be 1 to 7"
            )
    ratings = content.get("ratings") or {}
    if not isinstance(ratings, Mapping):
        raise SharedArtifactValidationError(
            "INVALID_RATINGS", "ratings must be an object"
        )
    return {
        "candidate_id": candidate_id,
        "rationale": rationale,
        "confidence": confidence,
        "ratings": dict(ratings),
        "decision_status": (
            str(content.get("decision_status") or "").strip() or None
        ),
    }


def _validate_followup(content: Mapping[str, Any]) -> dict[str, Any]:
    allocations = content.get("resource_allocation")
    actions = content.get("ranked_actions")
    plan = str(content.get("implementation_plan") or "").strip()
    if (
        not isinstance(allocations, list)
        or not allocations
        or not all(isinstance(item, Mapping) and item for item in allocations)
        or not isinstance(actions, list)
        or not actions
        or not all(str(item).strip() for item in actions)
        or not plan
    ):
        raise SharedArtifactValidationError(
            "INVALID_FOLLOWUP_CONTENT",
            "Follow-up requires resource allocation, ranked actions, and an implementation plan",
        )
    return {
        "resource_allocation": [dict(item) for item in allocations],
        "ranked_actions": [str(item).strip() for item in actions],
        "implementation_plan": plan,
    }
