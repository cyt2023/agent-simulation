from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import zipfile

from media_service.app.export import build_media_export
from media_service.app.timeline import RoomClock


def test_late_join_track_keeps_room_offset(repository):
    clock = RoomClock(
        clock_id="room-clock-session-1",
        origin_utc=datetime(2026, 7, 31, 0, 0, 0, tzinfo=timezone.utc),
        origin_monotonic_ms=0,
    )

    started = repository.recording_track_started(
        track_id="runtime-1-principal.wav",
        session_id="session-1",
        runtime_id="runtime-1",
        participant_id="principal",
        role="principal",
        room_name="study1-session-1-audio",
        clock_id=clock.clock_id,
        room_start_ms=90_000,
        started_at=clock.to_utc(90_000),
        codec="pcm_s16le",
        sample_rate_hz=48_000,
        content_type="audio/wav",
        consent_scope="study1_audio_recording_and_research_export",
    )
    finished = repository.recording_track_finished(
        "runtime-1-principal.wav",
        room_end_ms=92_500,
        ended_at=clock.to_utc(92_500),
        checksum="abc123",
        storage_uri="session-1/runtime-1-principal.wav",
        size_bytes=1024,
        duration_ms=2_500,
    )

    assert started.room_start_ms == 90_000
    assert started.started_at == clock.to_utc(90_000)
    assert finished.room_end_ms == 92_500
    assert finished.duration_ms == 2_500
    assert finished.status == "complete"


def test_export_manifest_uses_persisted_recording_tracks(repository, tmp_path):
    clock = RoomClock.start("session-1")
    repository.recording_track_started(
        track_id="runtime-1-teammate_1.wav",
        session_id="session-1",
        runtime_id="runtime-1",
        participant_id="teammate_1",
        role="teammate_1",
        room_name="study1-session-1-audio",
        clock_id=clock.clock_id,
        room_start_ms=1_200,
        started_at=clock.to_utc(1_200),
        codec="pcm_s16le",
        sample_rate_hz=48_000,
        content_type="audio/wav",
        consent_scope="study1_audio_recording_and_research_export",
    )
    repository.recording_track_finished(
        "runtime-1-teammate_1.wav",
        room_end_ms=2_200,
        ended_at=clock.to_utc(2_200),
        checksum="track-checksum",
        storage_uri="session-1/runtime-1-teammate_1.wav",
        size_bytes=2048,
        duration_ms=1_000,
    )

    payload = build_media_export(repository, "session-1", media_root=tmp_path)

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        manifest = json.loads(archive.read("recording_manifest.json"))

    assert manifest == [
        {
            "recording_id": "runtime-1-teammate_1.wav",
            "track_id": "runtime-1-teammate_1.wav",
            "runtime_id": "runtime-1",
            "participant_id": "teammate_1",
            "role": "teammate_1",
            "room_name": "study1-session-1-audio",
            "clock_id": clock.clock_id,
            "room_start_ms": 1_200,
            "room_end_ms": 2_200,
            "started_at_utc": clock.to_utc(1_200).isoformat().replace("+00:00", "Z"),
            "ended_at_utc": clock.to_utc(2_200).isoformat().replace("+00:00", "Z"),
            "duration_ms": 1_000,
            "size_bytes": 2048,
            "checksum": "track-checksum",
            "content_type": "audio/wav",
            "codec": "pcm_s16le",
            "sample_rate_hz": 48_000,
            "storage_uri": "session-1/runtime-1-teammate_1.wav",
            "consent_scope": "study1_audio_recording_and_research_export",
            "file_status": "complete",
        }
    ]
