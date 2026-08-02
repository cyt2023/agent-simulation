"""Validation and canonicalization for registered Study 1 tasks."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


TASK_ROLES = ("principal", "teammate_1", "teammate_2")
TASK_VALENCES = {"positive", "negative", "neutral"}
TASK_INFORMATION_TYPES = {"shared", "unique"}
MAX_TASK_IDENTIFIER_LENGTH = 128
MAX_TASK_VERSION_LENGTH = 64
MAX_TASK_TITLE_LENGTH = 512


class TaskDefinitionValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_registered_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical task definition or raise a stable validation error."""
    if not isinstance(payload, dict):
        raise TaskDefinitionValidationError(
            "INVALID_TASK_DEFINITION", "Task definition must be an object"
        )

    task_definition_id = str(payload.get("task_definition_id") or "").strip()
    task_version = str(payload.get("task_version") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not task_definition_id or not task_version or not title:
        raise TaskDefinitionValidationError(
            "INVALID_TASK_DEFINITION",
            "task_definition_id, task_version, and title are required",
        )
    if len(task_definition_id) > MAX_TASK_IDENTIFIER_LENGTH:
        raise TaskDefinitionValidationError(
            "TASK_IDENTIFIER_TOO_LONG",
            f"Task identifiers must be at most {MAX_TASK_IDENTIFIER_LENGTH} characters",
        )
    if len(task_version) > MAX_TASK_VERSION_LENGTH:
        raise TaskDefinitionValidationError(
            "TASK_VERSION_TOO_LONG",
            f"task_version must be at most {MAX_TASK_VERSION_LENGTH} characters",
        )
    if len(title) > MAX_TASK_TITLE_LENGTH:
        raise TaskDefinitionValidationError(
            "TASK_TITLE_TOO_LONG",
            f"Task title must be at most {MAX_TASK_TITLE_LENGTH} characters",
        )

    raw_candidate_ids = payload.get("candidate_ids")
    candidate_ids = (
        [str(value).strip() for value in raw_candidate_ids]
        if isinstance(raw_candidate_ids, list)
        else []
    )
    if any(len(value) > MAX_TASK_IDENTIFIER_LENGTH for value in candidate_ids):
        raise TaskDefinitionValidationError(
            "TASK_IDENTIFIER_TOO_LONG",
            f"Task identifiers must be at most {MAX_TASK_IDENTIFIER_LENGTH} characters",
        )
    if (
        len(candidate_ids) != 3
        or any(not value for value in candidate_ids)
        or len(set(candidate_ids)) != 3
    ):
        raise TaskDefinitionValidationError(
            "TASK_REQUIRES_THREE_UNIQUE_CANDIDATES",
            "A registered task requires exactly three unique candidate IDs",
        )

    raw_facts = payload.get("facts")
    if not isinstance(raw_facts, list) or not raw_facts:
        raise TaskDefinitionValidationError(
            "INVALID_TASK_FACTS", "A registered task requires atomic facts"
        )

    facts: list[dict[str, Any]] = []
    seen_fact_ids: set[str] = set()
    roles_with_facts: set[str] = set()
    for raw_fact in raw_facts:
        if not isinstance(raw_fact, dict):
            raise TaskDefinitionValidationError(
                "INVALID_TASK_FACTS", "Each atomic fact must be an object"
            )
        fact_id = str(raw_fact.get("fact_id") or "").strip()
        if not fact_id:
            raise TaskDefinitionValidationError(
                "INVALID_TASK_FACTS", "Each atomic fact requires a fact_id"
            )
        if len(fact_id) > MAX_TASK_IDENTIFIER_LENGTH:
            raise TaskDefinitionValidationError(
                "TASK_IDENTIFIER_TOO_LONG",
                f"Task identifiers must be at most {MAX_TASK_IDENTIFIER_LENGTH} characters",
            )
        if fact_id in seen_fact_ids:
            raise TaskDefinitionValidationError(
                "DUPLICATE_TASK_FACT_ID", "fact_id values must be globally unique"
            )
        seen_fact_ids.add(fact_id)

        candidate_id = str(raw_fact.get("candidate_id") or "").strip()
        if len(candidate_id) > MAX_TASK_IDENTIFIER_LENGTH:
            raise TaskDefinitionValidationError(
                "TASK_IDENTIFIER_TOO_LONG",
                f"Task identifiers must be at most {MAX_TASK_IDENTIFIER_LENGTH} characters",
            )
        if candidate_id not in candidate_ids:
            raise TaskDefinitionValidationError(
                "UNKNOWN_FACT_CANDIDATE",
                "Each fact must reference a registered candidate",
            )
        valence = str(raw_fact.get("valence") or "").strip()
        if valence not in TASK_VALENCES:
            raise TaskDefinitionValidationError(
                "INVALID_FACT_VALENCE",
                "Fact valence must be positive, negative, or neutral",
            )
        information_type = str(raw_fact.get("information_type") or "").strip()
        if information_type not in TASK_INFORMATION_TYPES:
            raise TaskDefinitionValidationError(
                "INVALID_FACT_INFORMATION_TYPE",
                "Fact information_type must be shared or unique",
            )
        text = str(raw_fact.get("text") or "").strip()
        if not text:
            raise TaskDefinitionValidationError(
                "INVALID_TASK_FACTS", "Each atomic fact requires text"
            )

        raw_visibility = raw_fact.get("visible_to_roles")
        visible_to_roles = (
            [str(value).strip() for value in raw_visibility]
            if isinstance(raw_visibility, list)
            else []
        )
        if (
            not visible_to_roles
            or len(set(visible_to_roles)) != len(visible_to_roles)
            or not set(visible_to_roles).issubset(TASK_ROLES)
        ):
            raise TaskDefinitionValidationError(
                "INVALID_FACT_VISIBILITY",
                "Fact visibility must be a non-empty set of participant roles",
            )
        roles_with_facts.update(visible_to_roles)
        facts.append(
            {
                "fact_id": fact_id,
                "candidate_id": candidate_id,
                "text": text,
                "valence": valence,
                "information_type": information_type,
                "visible_to_roles": sorted(visible_to_roles),
            }
        )

    if roles_with_facts != set(TASK_ROLES):
        raise TaskDefinitionValidationError(
            "INVALID_FACT_VISIBILITY",
            "Every participant role must receive at least one fact",
        )

    canonical = {
        "task_definition_id": task_definition_id,
        "task_version": task_version,
        "title": title,
        "candidate_ids": candidate_ids,
        "facts": facts,
    }
    checksum_payload = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        **copy.deepcopy(canonical),
        "content_checksum": hashlib.sha256(checksum_payload).hexdigest(),
    }
