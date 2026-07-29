"""Deterministic Study 1 ZIP export."""

from __future__ import annotations

import csv
import io
import json
import os
import zipfile
from datetime import date, datetime
from typing import Any

from .models import HUMAN_ROLES, PHASE_SCHEMA_VERSION
from .services import SUBMISSION_RULES, readiness, utc_iso

EXPORT_SCHEMA_VERSION = "1.0"


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return utc_iso(value if isinstance(value, datetime) else None)
    return str(value)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, indent=2, default=_json_default
    ).encode("utf-8")


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return (
        "\n".join(
            json.dumps(row, ensure_ascii=False, default=_json_default) for row in rows
        )
        + ("\n" if rows else "")
    ).encode("utf-8")


def _csv_bytes(fieldnames: list[str], rows: list[dict[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def build_study1_export(data: dict[str, Any]) -> io.BytesIO:
    session = data["session"]
    submissions = data.get("submissions") or []
    events = data.get("events") or []
    incidents = data.get("incidents") or []
    artifacts = data.get("artifacts") or []
    materials = data.get("materials") or []

    originals = [
        item for item in submissions if not item.get("previous_submission_id")
    ]
    submitted_keys = {
        (item["submission_type"], item["role"]) for item in originals
    }
    missing_submissions = []
    for submission_type, (_, roles) in SUBMISSION_RULES.items():
        if submission_type == "consent" and not session.get("require_consent"):
            continue
        for role in roles:
            if (submission_type, role.value) not in submitted_keys:
                missing_submissions.append(f"{submission_type}:{role.value}")
    artifact_types = {item["type"] for item in artifacts}
    missing_artifacts = [
        kind for kind in ("summary", "transcript") if kind not in artifact_types
    ]
    override_events = [
        event for event in events if event.get("event_type") == "override"
    ]

    participants = [
        {
            "session_id": session["session_id"],
            "participant_id": item["participant_id"],
            "role": item["role"],
            "online": item.get("online", False),
        }
        for item in session.get("participants") or []
    ]
    phase_events = [
        {
            "event_id": event["event_id"],
            "session_id": event["session_id"],
            "event_type": event["event_type"],
            "phase": event["phase"],
            "phase_version": event["phase_version"],
            "participant_id": event.get("participant_id"),
            "role": event.get("role"),
            "occurred_at": event.get("occurred_at"),
            "payload": json.dumps(
                event.get("payload") or {}, ensure_ascii=False, default=_json_default
            ),
        }
        for event in events
        if event.get("event_type") in ("phase_transition", "override")
    ]
    ui_events = [
        event for event in events if event.get("event_type") == "ui_event"
    ]
    incident_rows = [
        {
            "incident_id": item["incident_id"],
            "session_id": item["session_id"],
            "category": item["category"],
            "severity": item["severity"],
            "description": item["description"],
            "created_at": item["created_at"],
            "created_by": item["created_by"],
        }
        for item in incidents
    ]
    artifact_manifest = [
        {
            key: item.get(key)
            for key in (
                "artifact_id",
                "session_id",
                "type",
                "version",
                "storage_uri",
                "checksum",
                "created_at",
                "generator_version",
                "metadata",
            )
        }
        for item in artifacts
    ]
    material_assignment = [
        {
            key: item.get(key)
            for key in (
                "material_id",
                "session_id",
                "role",
                "title",
                "content",
                "storage_uri",
                "checksum",
                "created_at",
                "metadata",
            )
        }
        for item in materials
    ]
    schema = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "protocol_version": session.get("protocol_version"),
        "task_version": session.get("task_version"),
        "frontend_build_version": os.environ.get(
            "STUDY1_FRONTEND_BUILD_VERSION", "unknown"
        ),
        "backend_build_version": os.environ.get(
            "STUDY1_BACKEND_BUILD_VERSION", "unknown"
        ),
        "phase_schema_version": PHASE_SCHEMA_VERSION,
        "instrument_versions": sorted(
            {item["instrument_version"] for item in submissions}
        ),
        "artifact_versions": sorted(
            {f"{item['type']}:{item['version']}" for item in artifacts}
        ),
        "override_records": override_events,
        "missing_data": {
            "submissions": missing_submissions,
            "artifacts": missing_artifacts,
            "current_phase_prerequisites": readiness(session)[
                "missing_prerequisites"
            ],
        },
        "generated_at": utc_iso(),
    }
    integrity_report = {
        "complete": not (
            missing_submissions
            or missing_artifacts
            or incidents
            or schema["missing_data"]["current_phase_prerequisites"]
        ),
        "missing_submissions": missing_submissions,
        "missing_artifacts": missing_artifacts,
        "missing_current_phase_prerequisites": schema["missing_data"][
            "current_phase_prerequisites"
        ],
        "incident_count": len(incidents),
        "disconnect_events": [
            event
            for event in events
            if event.get("event_type") in ("participant_disconnected", "media_disconnected")
        ],
        "override_count": len(override_events),
        "configuration_checksum": session.get("configuration_checksum"),
        "generated_at": utc_iso(),
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("session.json", _json_bytes(session))
        archive.writestr(
            "participants.csv",
            _csv_bytes(
                ["session_id", "participant_id", "role", "online"], participants
            ),
        )
        archive.writestr(
            "phase_events.csv",
            _csv_bytes(
                [
                    "event_id",
                    "session_id",
                    "event_type",
                    "phase",
                    "phase_version",
                    "participant_id",
                    "role",
                    "occurred_at",
                    "payload",
                ],
                phase_events,
            ),
        )
        archive.writestr("submissions.jsonl", _jsonl_bytes(submissions))
        archive.writestr("ui_events.jsonl", _jsonl_bytes(ui_events))
        archive.writestr(
            "incidents.csv",
            _csv_bytes(
                [
                    "incident_id",
                    "session_id",
                    "category",
                    "severity",
                    "description",
                    "created_at",
                    "created_by",
                ],
                incident_rows,
            ),
        )
        archive.writestr("artifacts_manifest.json", _json_bytes(artifact_manifest))
        archive.writestr("materials_assignment.json", _json_bytes(material_assignment))
        archive.writestr("schema_version.json", _json_bytes(schema))
        archive.writestr("integrity_report.json", _json_bytes(integrity_report))
    buffer.seek(0)
    return buffer


def merge_media_export(
    workflow_bundle: io.BytesIO,
    media_bundle: bytes | None,
    media_error: str | None = None,
) -> io.BytesIO:
    """Copy B's bundle under media/ without trusting its filesystem paths."""
    output = io.BytesIO()
    workflow_bundle.seek(0)
    with zipfile.ZipFile(workflow_bundle, "r") as workflow, zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED
    ) as merged:
        for info in workflow.infolist():
            merged.writestr(info.filename, workflow.read(info.filename))
        if media_bundle:
            with zipfile.ZipFile(io.BytesIO(media_bundle), "r") as media:
                for info in media.infolist():
                    normalized = info.filename.replace("\\", "/").lstrip("/")
                    if ".." in normalized.split("/") or info.is_dir():
                        continue
                    merged.writestr(f"media/{normalized}", media.read(info.filename))
        elif media_error:
            merged.writestr(
                "media/media_export_error.json",
                _json_bytes({"error": "MEDIA_EXPORT_UNAVAILABLE", "message": media_error}),
            )
    output.seek(0)
    return output
