"""Typed Study 1 post-session markers."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime
from typing import Any

from .models import HUMAN_ROLES, Study1Role


PARTICIPANT_MARKER_TYPES = frozenset(
    {"confusing", "unexpected", "uncomfortable", "key_decision"}
)
RESEARCHER_MARKER_TYPES = frozenset({"technical", "other"})
ALL_MARKER_TYPES = PARTICIPANT_MARKER_TYPES | RESEARCHER_MARKER_TYPES


class MarkerValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalize_marker(
    *,
    session_id: str,
    actor: dict[str, Any],
    payload: dict[str, Any],
    created_at: datetime,
) -> dict[str, Any]:
    marker_type = str(payload.get("type") or "").strip()
    role = str(actor.get("role") or "")
    if role in {item.value for item in HUMAN_ROLES}:
        if marker_type not in PARTICIPANT_MARKER_TYPES:
            raise MarkerValidationError(
                "INVALID_MARKER_TYPE",
                "Participants may only submit confusing, unexpected, uncomfortable, or key_decision markers",
            )
    elif role == Study1Role.RESEARCHER.value:
        if marker_type not in ALL_MARKER_TYPES:
            raise MarkerValidationError(
                "INVALID_MARKER_TYPE", "Marker type is not registered"
            )
    else:
        raise MarkerValidationError("FORBIDDEN", "Marker actor is not allowed")

    reason = str(payload.get("reason") or payload.get("note") or "").strip()
    if not reason:
        raise MarkerValidationError(
            "MARKER_REASON_REQUIRED", "A marker reason is required"
        )

    start_ms = _normalize_non_negative_int(payload.get("start_ms"), "start_ms")
    end_ms = _normalize_non_negative_int(payload.get("end_ms"), "end_ms")
    if end_ms < start_ms:
        raise MarkerValidationError(
            "INVALID_MARKER_RANGE", "end_ms must be greater than or equal to start_ms"
        )

    participant_visible = payload.get("participant_visible")
    if participant_visible is None:
        participant_visible = role in {item.value for item in HUMAN_ROLES}

    return {
        "marker_id": str(payload.get("marker_id") or uuid.uuid4()),
        "session_id": session_id,
        "marker_type": marker_type,
        "type": marker_type,
        "source": (
            "researcher_marker"
            if role == Study1Role.RESEARCHER.value
            else "participant_marker"
        ),
        "participant_id": str(actor.get("participant_id") or ""),
        "role": role,
        "participant_visible": bool(participant_visible),
        "start_ms": start_ms,
        "end_ms": end_ms,
        "segment_ids": _normalize_string_list(payload.get("segment_ids")),
        "recording_ids": _normalize_string_list(payload.get("recording_ids")),
        "reason": reason,
        "created_at": created_at,
        "metadata": copy.deepcopy(payload.get("metadata") or {}),
    }


def marker_visible_to_actor(marker: dict[str, Any], actor: dict[str, Any]) -> bool:
    if actor.get("role") == Study1Role.RESEARCHER.value:
        return True
    if marker.get("participant_id") == actor.get("participant_id"):
        return True
    return bool(marker.get("participant_visible"))


def _normalize_non_negative_int(value: Any, field: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise MarkerValidationError(
            "INVALID_MARKER_RANGE", f"{field} must be a non-negative integer"
        ) from error
    if number < 0:
        raise MarkerValidationError(
            "INVALID_MARKER_RANGE", f"{field} must be a non-negative integer"
        )
    return number


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise MarkerValidationError(
            "INVALID_MARKER_REFERENCE", "marker references must be lists"
        )
    return [item for item in (str(item).strip() for item in value) if item]
