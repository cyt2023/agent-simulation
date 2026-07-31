from __future__ import annotations

import io
import json
import zipfile


def _zip_bundle() -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "export_manifest.json",
            json.dumps(
                {
                    "schema_version": "study1-export-v2",
                    "session_id": "session-1",
                    "checksums": {},
                    "build_versions": {
                        "backend": "backend-sha",
                        "frontend": "frontend-sha",
                        "media_service": "media-sha",
                    },
                }
            ),
        )
        archive.writestr(
            "media_manifest.json",
            json.dumps(
                {
                    "recordings": [
                        {
                            "recording_id": "rec-1",
                            "clock_id": "room-clock-1",
                        }
                    ]
                }
            ),
        )
        archive.writestr(
            "normalized/utterances.jsonl",
            json.dumps(
                {
                    "utterance_id": "u-1",
                    "recording_id": "rec-1",
                    "clock_id": "room-clock-1",
                    "text": "Candidate A was discussed.",
                }
            )
            + "\n",
        )
        archive.writestr(
            "normalized/markers.jsonl",
            json.dumps(
                {
                    "marker_id": "m-1",
                    "segment_ids": ["u-1"],
                    "recording_ids": ["rec-1"],
                }
            )
            + "\n",
        )
        archive.writestr(
            "integrity_report.json",
            json.dumps({"errors": [], "certification_status": "certifiable"}),
        )
    buffer.seek(0)
    return buffer


def test_acceptance_reconstructs_export_relationships():
    from scripts.verify_study1_release import reconstruct_study1_export

    result = reconstruct_study1_export(_zip_bundle())

    assert result.status == "reconstructable"
    assert result.utterance_count == 1
    assert result.recording_count == 1
    assert result.marker_count == 1
