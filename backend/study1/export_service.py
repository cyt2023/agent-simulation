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
from .formal_projection import formal_readiness, project_formal_session
from .instruments import load_instrument_catalog
from .export_schema import (
    CANONICAL_EXPORT_SCHEMA_VERSION,
    build_export_manifest,
    checksum_bytes,
)
from .integrity_service import build_integrity_report
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


def _artifact_content_json(artifact: dict[str, Any]) -> Any:
    try:
        return json.loads(artifact.get("content") or "")
    except (TypeError, json.JSONDecodeError):
        return None


def _latest_artifact(artifacts: list[dict[str, Any]], artifact_type: str) -> dict[str, Any] | None:
    matches = [item for item in artifacts if item.get("type") == artifact_type]
    return matches[-1] if matches else None


def _normalized_utterances(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transcript = _latest_artifact(artifacts, "transcript")
    if not transcript:
        return []
    parsed = _artifact_content_json(transcript)
    if isinstance(parsed, list):
        rows = parsed
    else:
        rows = [
            {
                "segment_id": f"legacy-line-{index}",
                "speaker": "unknown",
                "text": line,
                "start_ms": None,
                "end_ms": None,
            }
            for index, line in enumerate(
                str(transcript.get("content") or "").splitlines(), start=1
            )
            if line.strip()
        ]
    utterances: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        utterance_id = str(
            row.get("utterance_id") or row.get("segment_id") or f"utterance-{index}"
        )
        recording_id = row.get("recording_id")
        clock_id = row.get("clock_id") or (
            f"clock:{recording_id}" if recording_id else "room-clock-unknown"
        )
        utterances.append(
            {
                "utterance_id": utterance_id,
                "segment_id": utterance_id,
                "session_id": transcript.get("session_id"),
                "speaker": row.get("speaker") or row.get("role") or "unknown",
                "text": row.get("text") or row.get("content") or "",
                "start_ms": row.get("start_ms"),
                "end_ms": row.get("end_ms"),
                "recording_id": recording_id,
                "clock_id": clock_id,
                "source_artifact_id": transcript.get("artifact_id"),
            }
        )
    return utterances


def _media_manifest(
    artifacts: list[dict[str, Any]], utterances: list[dict[str, Any]]
) -> dict[str, Any]:
    transcript = _latest_artifact(artifacts, "transcript") or {}
    metadata = transcript.get("metadata") or {}
    manifest = metadata.get("recording_manifest")
    if isinstance(manifest, list) and manifest:
        recordings = manifest
    else:
        recordings = []
        seen: set[str] = set()
        for utterance in utterances:
            recording_id = utterance.get("recording_id")
            if not recording_id or recording_id in seen:
                continue
            seen.add(recording_id)
            recordings.append(
                {
                    "recording_id": recording_id,
                    "clock_id": utterance.get("clock_id") or f"clock:{recording_id}",
                    "content_type": "audio/wav",
                    "status": "metadata_only",
                }
            )
    return {
        "schema_version": "study1-media-manifest-v1",
        "recordings": recordings,
        "utterance_count": len(utterances),
    }


def _normalized_review_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if (event.get("payload") or {}).get("ui_event_type")
        in {
            "review_page_enter",
            "review_page_leave",
            "summary_visible",
            "transcript_expand",
            "transcript_collapse",
            "transcript_segment_view",
            "scroll_depth",
            "active_reading_time",
            "review_telemetry_batch",
            "recording_replay",
        }
    ]


def build_study1_export(data: dict[str, Any]) -> io.BytesIO:
    raw_session = data["session"]
    is_formal = raw_session.get("protocol_mode") == "formal_v2"
    session = (
        project_formal_session(raw_session, data)
        if is_formal
        else raw_session
    )
    submissions = data.get("submissions") or []
    events = data.get("events") or []
    incidents = data.get("incidents") or []
    artifacts = data.get("artifacts") or []
    materials = data.get("materials") or []
    markers = data.get("markers") or []
    replay_plans = data.get("replay_plans") or []
    decisions = data.get("decisions") or []
    instrument_responses = data.get("instrument_responses") or []
    utterances = _normalized_utterances(artifacts)
    media_manifest = _media_manifest(artifacts, utterances)

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
    current_state = formal_readiness(session) if is_formal else readiness(session)
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
        "formal_certifiable": bool(
            is_formal and session.get("formal_certifiable", False)
        ),
        "certification_status": (
            "certifiable"
            if is_formal and session.get("formal_certifiable", False)
            else "uncertifiable"
        ),
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
            "current_phase_prerequisites": current_state["missing_prerequisites"],
        },
        "generated_at": utc_iso(),
    }
    generated_at = utc_iso()
    integrity_report = build_integrity_report(
        missing_submissions=missing_submissions,
        missing_artifacts=missing_artifacts,
        missing_current_phase_prerequisites=schema["missing_data"][
            "current_phase_prerequisites"
        ],
        incidents=incidents,
        override_events=override_events,
        media_manifest=media_manifest,
        configuration_checksum=session.get("configuration_checksum"),
        generated_at=generated_at,
    )
    integrity_report["disconnect_events"] = [
        event
        for event in events
        if event.get("event_type") in ("participant_disconnected", "media_disconnected")
    ]
    canonical_files = {
        "media_manifest.json": _json_bytes(media_manifest),
        "normalized/events.jsonl": _jsonl_bytes(events),
        "normalized/utterances.jsonl": _jsonl_bytes(utterances),
        "normalized/markers.jsonl": _jsonl_bytes(markers),
        "normalized/replay_plans.json": _json_bytes(replay_plans),
        "normalized/decisions.jsonl": _jsonl_bytes(decisions),
        "normalized/instrument_responses.jsonl": _jsonl_bytes(instrument_responses),
        "normalized/review_events.jsonl": _jsonl_bytes(
            _normalized_review_events(events)
        ),
        "normalized/incidents.jsonl": _jsonl_bytes(incidents),
        "normalized/materials.jsonl": _jsonl_bytes(materials),
        "normalized/artifacts.jsonl": _jsonl_bytes(artifact_manifest),
        "normalized/summary_qa.jsonl": _jsonl_bytes(
            [item for item in artifacts if item.get("type") == "summary_qa"]
        ),
    }
    export_manifest = build_export_manifest(
        session=session,
        file_checksums={
            name: checksum_bytes(payload) for name, payload in canonical_files.items()
        },
        formal_certifiable=bool(is_formal and session.get("formal_certifiable", False)),
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("export_manifest.json", _json_bytes(export_manifest))
        for name, payload in canonical_files.items():
            archive.writestr(name, payload)
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
        archive.writestr("markers.jsonl", _jsonl_bytes(markers))
        archive.writestr("replay_plans.json", _json_bytes(replay_plans))
        if is_formal:
            task_definition = data.get("task_definition") or {
                "task_definition_id": session.get("task_definition_id"),
                "task_version": session.get("task_version"),
                "title": session.get("session_name"),
                "candidate_ids": session.get("candidate_ids") or [],
                "facts": [],
            }
            task_facts = task_definition.get("facts") or []
            catalog = load_instrument_catalog()
            ordered_instruments = {
                "catalog_version": catalog.get("catalog_version"),
                "catalog_checksum": catalog.get("checksum"),
                "instruments": catalog.get("instruments") or [],
                "responses": data.get("instrument_responses") or [],
            }
            archive.writestr("task_definition.json", _json_bytes(task_definition))
            archive.writestr("task_facts.jsonl", _jsonl_bytes(task_facts))
            archive.writestr(
                "role_assignments.jsonl",
                _jsonl_bytes(data.get("role_assignments") or []),
            )
            archive.writestr(
                "fact_assignments.jsonl",
                _jsonl_bytes(data.get("fact_assignments") or []),
            )
            archive.writestr(
                "protocol_snapshot.json",
                _json_bytes(data.get("protocol_snapshot") or {}),
            )
            archive.writestr(
                "decisions.jsonl",
                _jsonl_bytes(data.get("decisions") or []),
            )
            archive.writestr(
                "shared_artifacts.json",
                _json_bytes(data.get("shared_artifacts") or []),
            )
            archive.writestr(
                "shared_revisions.jsonl",
                _jsonl_bytes(data.get("shared_revisions") or []),
            )
            archive.writestr(
                "shared_confirmations.jsonl",
                _jsonl_bytes(data.get("shared_confirmations") or []),
            )
            archive.writestr(
                "ordered_instruments.json",
                _json_bytes(ordered_instruments),
            )
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
