"""Controlled Study 1 retention and withdrawal workflow."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _checksum(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class RetentionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RetentionTombstone:
    session_id: str
    job_id: str
    executed_at: str
    approved_by: str
    reason_code: str
    manifest_checksum: str
    subject_count: int

    def public_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "job_id": self.job_id,
            "executed_at": self.executed_at,
            "approved_by": self.approved_by,
            "reason_code": self.reason_code,
            "manifest_checksum": self.manifest_checksum,
            "subject_count": self.subject_count,
        }


@dataclass
class RetentionJob:
    job_id: str
    session_id: str
    status: str
    requested_by: str
    created_at: str
    manifest: dict[str, Any]
    manifest_checksum: str
    subject_pseudo_ids: list[str] = field(default_factory=list)
    executed_at: str | None = None
    approved_by: str | None = None
    reason: str | None = None

    def public_dict(self, *, include_subjects: bool = False) -> dict[str, Any]:
        payload = {
            "job_id": self.job_id,
            "session_id": self.session_id,
            "status": self.status,
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "manifest": copy.deepcopy(self.manifest),
            "manifest_checksum": self.manifest_checksum,
            "executed_at": self.executed_at,
            "approved_by": self.approved_by,
            "reason": self.reason,
        }
        if include_subjects:
            payload["subject_pseudo_ids"] = list(self.subject_pseudo_ids)
        else:
            payload["subject_count"] = len(self.subject_pseudo_ids)
        return payload


class RetentionStore(Protocol):
    def put_job(self, job: RetentionJob) -> None: ...

    def get_job(self, job_id: str) -> RetentionJob | None: ...

    def put_tombstone(self, tombstone: RetentionTombstone) -> None: ...

    def tombstones(self, session_id: str) -> list[RetentionTombstone]: ...


class InMemoryRetentionStore:
    def __init__(self):
        self.jobs: dict[str, RetentionJob] = {}
        self._tombstones: list[RetentionTombstone] = []

    def put_job(self, job: RetentionJob) -> None:
        self.jobs[job.job_id] = copy.deepcopy(job)

    def get_job(self, job_id: str) -> RetentionJob | None:
        job = self.jobs.get(job_id)
        return copy.deepcopy(job) if job else None

    def put_tombstone(self, tombstone: RetentionTombstone) -> None:
        self._tombstones.append(copy.deepcopy(tombstone))

    def tombstones(self, session_id: str) -> list[RetentionTombstone]:
        return [
            copy.deepcopy(item)
            for item in self._tombstones
            if item.session_id == session_id
        ]


class MediaCommandGateway(Protocol):
    def send_command(self, envelope: dict[str, Any]) -> dict[str, Any]: ...


class RetentionService:
    def __init__(
        self,
        *,
        store: RetentionStore | None = None,
        media_gateway: MediaCommandGateway | None = None,
    ):
        self.store = store or InMemoryRetentionStore()
        self.media_gateway = media_gateway

    def create_dry_run(
        self,
        session_id: str,
        *,
        requested_by: str,
        subject_pseudo_ids: list[str] | None = None,
        reason_code: str = "participant_withdrawal",
        scope: str = "session_media_and_identity",
    ) -> RetentionJob:
        if not session_id:
            raise RetentionError("SESSION_REQUIRED", "session_id is required")
        subject_pseudo_ids = sorted({str(item) for item in subject_pseudo_ids or [] if str(item)})
        manifest = {
            "manifest_version": "study1-retention-v1",
            "session_id": session_id,
            "scope": scope,
            "reason_code": reason_code,
            "actions": [
                "purge_media_artifacts",
                "purge_transcripts",
                "purge_identity_vault_rows",
                "write_non_identifying_tombstone",
            ],
            "subject_count": len(subject_pseudo_ids),
        }
        job = RetentionJob(
            job_id=str(uuid.uuid4()),
            session_id=session_id,
            status="dry_run",
            requested_by=requested_by,
            created_at=_utc_iso(),
            manifest=manifest,
            manifest_checksum=_checksum(manifest),
            subject_pseudo_ids=subject_pseudo_ids,
        )
        self.store.put_job(job)
        return job

    def get_job(self, job_id: str) -> RetentionJob:
        job = self.store.get_job(job_id)
        if job is None:
            raise RetentionError("RETENTION_JOB_NOT_FOUND", "Retention job not found")
        return job

    def execute(
        self,
        job_id: str,
        *,
        approved_manifest_checksum: str,
        approved_by: str,
        reason: str,
        phase_version: int = 1,
    ) -> RetentionJob:
        job = self.get_job(job_id)
        if job.status != "dry_run":
            raise RetentionError(
                "RETENTION_JOB_NOT_EXECUTABLE",
                "Only dry-run retention jobs can be executed",
            )
        if approved_manifest_checksum != job.manifest_checksum:
            raise RetentionError(
                "RETENTION_CHECKSUM_MISMATCH",
                "The approved manifest checksum does not match the dry run",
            )
        if not approved_by or not reason.strip():
            raise RetentionError(
                "RETENTION_APPROVAL_REQUIRED",
                "A second approval actor and reason are required",
            )
        if self.media_gateway:
            self.media_gateway.send_command(
                {
                    "command_id": str(
                        uuid.uuid5(uuid.NAMESPACE_URL, f"study1-retention:{job.job_id}")
                    ),
                    "session_id": job.session_id,
                    "phase_version": max(1, int(phase_version or 1)),
                    "command": "PURGE_SESSION_MEDIA",
                    "issued_at": _utc_iso(),
                    "payload": {
                        "retention_job_id": job.job_id,
                        "manifest_checksum": job.manifest_checksum,
                        "reason": reason,
                        "reason_code": job.manifest.get("reason_code"),
                    },
                }
            )
        job.status = "executed"
        job.executed_at = _utc_iso()
        job.approved_by = approved_by
        job.reason = reason
        self.store.put_job(job)
        self.store.put_tombstone(
            RetentionTombstone(
                session_id=job.session_id,
                job_id=job.job_id,
                executed_at=job.executed_at,
                approved_by=approved_by,
                reason_code=str(job.manifest.get("reason_code") or ""),
                manifest_checksum=job.manifest_checksum,
                subject_count=len(job.subject_pseudo_ids),
            )
        )
        return job

    def tombstones(self, session_id: str) -> list[RetentionTombstone]:
        return self.store.tombstones(session_id)
