from __future__ import annotations

from media_service.app.rtc_metrics import RtcMetricsService


def test_rtc_metric_batch_is_persisted_and_aggregated(repository):
    service = RtcMetricsService(repository)

    snapshot = service.record_batch(
        session_id="session-1",
        phase_version=4,
        participant_id="p-1",
        role="principal",
        samples=[
            {
                "rtt_ms": 30,
                "jitter_ms": 5,
                "packet_loss": 0.0,
                "bitrate_kbps": 48,
                "connection_state": "connected",
            },
            {
                "rtt_ms": 70,
                "jitter_ms": 8,
                "packet_loss": 0.0,
                "bitrate_kbps": 48,
                "connection_state": "connected",
            },
        ],
    )

    rows = repository.list_session_rtc_metrics("session-1")
    assert len(rows) == 2
    assert rows[0].participant_id == "p-1"
    assert snapshot["status"] == "healthy"
    assert snapshot["sample_count"] == 2
    assert snapshot["p50_rtt_ms"] == 50
    assert snapshot["p95_rtt_ms"] == 70


def test_rtc_metric_packet_loss_degrades_snapshot(repository):
    service = RtcMetricsService(repository)

    snapshot = service.record_batch(
        session_id="session-1",
        phase_version=4,
        participant_id="t1",
        role="teammate_1",
        samples=[
            {
                "rtt_ms": 80,
                "packet_loss": 0.12,
                "connection_state": "connected",
            }
        ],
    )

    assert snapshot["status"] == "degraded"
