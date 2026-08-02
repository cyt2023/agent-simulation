from study1.integrity_service import build_integrity_report


def test_integrity_report_flags_missing_media():
    report = build_integrity_report(
        missing_submissions=[],
        missing_artifacts=[],
        missing_current_phase_prerequisites=[],
        incidents=[],
        override_events=[],
        media_manifest={"recordings": []},
        configuration_checksum="checksum",
        generated_at="2026-07-31T00:00:00Z",
    )

    assert report["complete"] is False
    assert "MEDIA_EXPORT_UNAVAILABLE" in report["errors"]


def test_integrity_report_is_certifiable_when_required_records_exist():
    report = build_integrity_report(
        missing_submissions=[],
        missing_artifacts=[],
        missing_current_phase_prerequisites=[],
        incidents=[],
        override_events=[],
        media_manifest={"recordings": [{"recording_id": "rec-1"}]},
        configuration_checksum="checksum",
        generated_at="2026-07-31T00:00:00Z",
    )

    assert report["complete"] is True
    assert report["certification_status"] == "certifiable"
