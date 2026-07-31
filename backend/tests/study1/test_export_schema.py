import io
import json
import zipfile

from study1.export_service import build_study1_export


def _jsonl(archive, name):
    content = archive.read(name).decode("utf-8").strip()
    return [json.loads(line) for line in content.splitlines()] if content else []


def _data():
    return {
        "session": {
            "session_id": "s-export",
            "session_name": "Export",
            "experiment_type": "study1",
            "protocol_version": "study1-a-1.0",
            "phase_schema_version": "1.0",
            "phase": "COMPLETED",
            "phase_version": 9,
            "status": "completed",
            "participants": [],
            "completion": {},
        },
        "events": [
            {
                "event_id": "e-1",
                "session_id": "s-export",
                "event_type": "ui_event",
                "phase": "REVIEW",
                "phase_version": 7,
                "occurred_at": "2026-07-31T00:00:00Z",
                "payload": {"ui_event_type": "scroll_depth", "max_depth": 1},
            }
        ],
        "submissions": [],
        "artifacts": [
            {
                "artifact_id": "transcript-1",
                "session_id": "s-export",
                "type": "transcript",
                "version": "1",
                "content": json.dumps(
                    [
                        {
                            "segment_id": "u-1",
                            "speaker": "teammate_1",
                            "text": "I think candidate A is strongest.",
                            "start_ms": 10_000,
                            "end_ms": 12_000,
                            "recording_id": "rec-1",
                            "clock_id": "room-clock-1",
                        }
                    ]
                ),
                "checksum": "transcript-checksum",
                "created_at": "2026-07-31T00:00:01Z",
                "generator_version": "test",
                "metadata": {
                    "recording_manifest": [
                        {
                            "recording_id": "rec-1",
                            "clock_id": "room-clock-1",
                            "content_type": "audio/wav",
                        }
                    ]
                },
            }
        ],
        "incidents": [],
        "materials": [],
        "markers": [
            {
                "marker_id": "m-1",
                "session_id": "s-export",
                "type": "key_decision",
                "marker_type": "key_decision",
                "start_ms": 10_000,
                "end_ms": 12_000,
                "segment_ids": ["u-1"],
                "recording_ids": ["rec-1"],
                "reason": "Important decision.",
                "created_at": "2026-07-31T00:00:02Z",
            }
        ],
        "replay_plans": [
            {
                "replay_plan_id": "rp-1",
                "session_id": "s-export",
                "version": "1",
                "source_marker_ids": ["m-1"],
                "items": [
                    {
                        "item_id": "rpi-1",
                        "start_ms": 0,
                        "end_ms": 22_000,
                        "marker_ids": ["m-1"],
                        "segment_ids": ["u-1"],
                    }
                ],
            }
        ],
        "decisions": [
            {
                "decision_id": "d-1",
                "session_id": "s-export",
                "decision_kind": "team_final",
                "candidate_id": "a",
                "rationale": "Evidence converged.",
                "created_at": "2026-07-31T00:00:03Z",
            }
        ],
        "instrument_responses": [],
    }


def test_export_contains_canonical_manifest_and_joinable_records():
    bundle = build_study1_export(_data())

    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert {
            "export_manifest.json",
            "media_manifest.json",
            "normalized/events.jsonl",
            "normalized/utterances.jsonl",
            "normalized/markers.jsonl",
            "normalized/replay_plans.json",
            "normalized/decisions.jsonl",
            "normalized/review_events.jsonl",
        } <= names
        manifest = json.loads(archive.read("export_manifest.json"))
        utterance = _jsonl(archive, "normalized/utterances.jsonl")[0]
        marker = _jsonl(archive, "normalized/markers.jsonl")[0]
        media_manifest = json.loads(archive.read("media_manifest.json"))

    assert manifest["schema_version"] == "study1-export-v2"
    assert manifest["build_versions"]["backend"] != ""
    assert utterance["clock_id"] == media_manifest["recordings"][0]["clock_id"]
    assert marker["segment_ids"] == [utterance["utterance_id"]]


def test_export_integrity_reports_missing_media_bundle():
    data = _data()
    data["artifacts"] = []

    bundle = build_study1_export(data)

    with zipfile.ZipFile(bundle) as archive:
        report = json.loads(archive.read("integrity_report.json"))

    assert "MEDIA_EXPORT_UNAVAILABLE" in report["errors"]
