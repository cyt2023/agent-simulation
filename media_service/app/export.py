from __future__ import annotations

from datetime import date, datetime
import io
import json
from pathlib import Path
import hashlib
import zipfile

from sqlalchemy.inspection import inspect

from .repository import MediaRepository


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _row_dict(row) -> dict:
    return {column.key: getattr(row, column.key) for column in inspect(row).mapper.column_attrs}


def _json_bytes(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, indent=2, default=_json_default
    ).encode("utf-8")


def _jsonl_bytes(rows) -> bytes:
    content = "\n".join(
        json.dumps(_row_dict(row), ensure_ascii=False, default=_json_default)
        for row in rows
    )
    return (content + ("\n" if content else "")).encode("utf-8")


def build_media_export(
    repository: MediaRepository,
    session_id: str,
    *,
    media_root: str | Path | None = None,
) -> bytes:
    commands = repository.list_session_commands(session_id)
    runtimes = repository.list_session_runtimes(session_id)
    outbox = repository.list_session_outbox(session_id)
    connections = repository.list_session_connections(session_id)
    segments = repository.list_session_segments(session_id)
    artifacts = repository.list_session_artifacts(session_id)
    summary_attempts = repository.list_session_summary_attempts(session_id)
    agent_turns = repository.list_session_agent_turns(session_id)
    incidents = repository.list_session_incidents(session_id)
    status = {
        "session_id": session_id,
        "runtime_count": len(runtimes),
        "active_runtime": next(
            (runtime.runtime_id for runtime in reversed(runtimes) if runtime.ended_at is None),
            None,
        ),
        "pending_callback_count": len(
            [message for message in outbox if message.delivered_at is None]
        ),
    }
    transcript = [_row_dict(row) for row in segments]
    agent_segments = [row for row in segments if row.speaker == "proxy"]
    summaries = [
        _row_dict(row) for row in artifacts if row.kind == "summary"
    ]
    recordings = []
    recording_files: list[Path] = []
    if media_root:
        session_root = (Path(media_root) / session_id).resolve()
        if session_root.is_dir():
            recording_files = sorted(session_root.glob("*.wav"))
            for path in recording_files:
                payload = path.read_bytes()
                recordings.append(
                    {
                        "recording_id": path.name,
                        "size": len(payload),
                        "checksum": hashlib.sha256(payload).hexdigest(),
                        "content_type": "audio/wav",
                    }
                )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("media_status.json", _json_bytes(status))
        archive.writestr("commands.jsonl", _jsonl_bytes(commands))
        archive.writestr("runtime_events.jsonl", _jsonl_bytes(outbox))
        archive.writestr("connections.jsonl", _jsonl_bytes(connections))
        archive.writestr("transcript.json", _json_bytes(transcript))
        archive.writestr("summary.json", _json_bytes(summaries))
        archive.writestr("summary_attempts.jsonl", _jsonl_bytes(summary_attempts))
        archive.writestr("agent_turns.jsonl", _jsonl_bytes(agent_turns))
        archive.writestr("recording_manifest.json", _json_bytes(recordings))
        archive.writestr("agent_log.jsonl", _jsonl_bytes(agent_segments))
        archive.writestr("incidents.jsonl", _jsonl_bytes(incidents))
        for path in recording_files:
            archive.write(path, f"recordings/{path.name}")
    return buffer.getvalue()
