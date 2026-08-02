from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


SUMMARY_FAILURE_ACTIONS = {"retry_same_config", "transcript_only", "terminate"}
SUMMARY_QA_ERROR_FIELDS = (
    "omission_error",
    "misattribution_error",
    "hallucination_error",
    "decision_status_error",
    "action_item_error",
)


class SummaryPolicyError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_summary_failure_action(
    *,
    action: str,
    reason: str,
    frozen_config_checksum: str | None = None,
    approved_config_checksum: str | None = None,
    source_transcript_checksum: str | None = None,
    source_summary_version: str | None = None,
) -> dict[str, Any]:
    clean_action = str(action or "")
    clean_reason = str(reason or "").strip()
    if clean_action not in SUMMARY_FAILURE_ACTIONS:
        raise SummaryPolicyError("SUMMARY_ACTION_INVALID", "Unknown Summary failure action")
    if not clean_reason:
        raise SummaryPolicyError(
            "SUMMARY_ACTION_REASON_REQUIRED",
            "Summary failure actions require a non-empty reason",
        )
    if clean_action == "retry_same_config":
        if not source_transcript_checksum or not source_summary_version:
            raise SummaryPolicyError(
                "SUMMARY_RETRY_SOURCE_REQUIRED",
                "Retry requires source transcript checksum and summary version",
            )
        if frozen_config_checksum != approved_config_checksum:
            raise SummaryPolicyError(
                "SUMMARY_CONFIG_DRIFT",
                "Retry must use the frozen Summary configuration",
            )
        return {
            "action": clean_action,
            "media_command": "REGENERATE_SUMMARY",
            "payload": {
                "reason": clean_reason,
                "source_transcript_checksum": source_transcript_checksum,
                "source_summary_version": source_summary_version,
                "frozen_config_checksum": frozen_config_checksum,
            },
        }
    return {
        "action": clean_action,
        "media_command": None,
        "payload": {"reason": clean_reason},
    }


@dataclass(frozen=True)
class SummaryQaEntry:
    qa_id: str
    session_id: str
    summary_artifact_id: str
    researcher_id: str
    ratings: dict[str, Any]
    private: bool
    created_at: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "qa_id": self.qa_id,
            "session_id": self.session_id,
            "summary_artifact_id": self.summary_artifact_id,
            "researcher_id": self.researcher_id,
            "ratings": copy.deepcopy(self.ratings),
            "private": self.private,
            "created_at": self.created_at,
        }


class SummaryQaStore(Protocol):
    def append(self, entry: SummaryQaEntry) -> None: ...

    def list_for_session(self, session_id: str) -> list[SummaryQaEntry]: ...


class InMemorySummaryQaStore:
    def __init__(self):
        self.entries: list[SummaryQaEntry] = []

    def append(self, entry: SummaryQaEntry) -> None:
        self.entries.append(entry)

    def list_for_session(self, session_id: str) -> list[SummaryQaEntry]:
        return [
            copy.deepcopy(entry)
            for entry in self.entries
            if entry.session_id == session_id
        ]


class SummaryQaService:
    def __init__(self, *, store: SummaryQaStore | None = None):
        self.store = store or InMemorySummaryQaStore()

    def record(
        self,
        *,
        session_id: str,
        summary_artifact_id: str,
        researcher_id: str,
        ratings: dict[str, Any],
    ) -> SummaryQaEntry:
        clean = {
            field: bool(ratings.get(field))
            for field in SUMMARY_QA_ERROR_FIELDS
        }
        note = str(ratings.get("note") or "").strip()
        clean["note"] = note[:1000]
        if any(clean[field] for field in SUMMARY_QA_ERROR_FIELDS) and not note:
            raise SummaryPolicyError(
                "SUMMARY_QA_NOTE_REQUIRED",
                "A note is required when a Summary QA error flag is selected",
            )
        entry = SummaryQaEntry(
            qa_id=str(uuid.uuid4()),
            session_id=session_id,
            summary_artifact_id=summary_artifact_id,
            researcher_id=researcher_id,
            ratings=clean,
            private=True,
            created_at=_utc_iso(),
        )
        self.store.append(entry)
        return entry

    def list_for_session(self, session_id: str) -> list[SummaryQaEntry]:
        return self.store.list_for_session(session_id)
