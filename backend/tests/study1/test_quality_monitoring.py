RESEARCHER = {"participant_id": "researcher", "role": "researcher"}
PRINCIPAL = {"participant_id": "principal-1", "role": "principal"}


def test_stale_rtc_metric_is_reported_unknown(memory_service):
    session_id = memory_service.create_session("quality")["session"]["session_id"]

    memory_service.record_quality_metrics(
        session_id,
        PRINCIPAL,
        {
            "observed_at": "2020-01-01T00:00:00Z",
            "rtt_ms": 30,
            "jitter_ms": 5,
            "packet_loss": 0.0,
            "bitrate_kbps": 48,
            "connection_state": "connected",
        },
    )

    snapshot = memory_service.quality_snapshot(session_id, RESEARCHER)

    assert snapshot["rtc"]["status"] == "unknown"
    assert snapshot["rtc"]["stale_participant_count"] == 1


def test_recent_rtc_metric_aggregates_latency(memory_service):
    session_id = memory_service.create_session("quality")["session"]["session_id"]

    memory_service.record_quality_metrics(
        session_id,
        PRINCIPAL,
        {
            "rtt_ms": 30,
            "jitter_ms": 5,
            "packet_loss": 0.0,
            "bitrate_kbps": 48,
            "connection_state": "connected",
        },
    )

    snapshot = memory_service.quality_snapshot(session_id, RESEARCHER)

    assert snapshot["rtc"]["status"] == "healthy"
    assert snapshot["rtc"]["p50_rtt_ms"] == 30
    assert snapshot["components"]["asr"]["status"] == "unknown"


def test_quality_metrics_are_forwarded_to_b_with_authoritative_identity(memory_service):
    session_id = memory_service.create_session("quality-forward")["session"]["session_id"]

    event = memory_service.record_quality_metrics(
        session_id,
        PRINCIPAL,
        {
            "rtt_ms": 42,
            "jitter_ms": 6,
            "packet_loss": 0.0,
            "bitrate_kbps": 50,
            "connection_state": "connected",
        },
    )

    assert event["payload"]["participant_id"] == "principal-1"
    batch = memory_service.media_gateway.rtc_metric_batches[0]
    assert batch["session_id"] == session_id
    assert batch["phase_version"] == 1
    assert batch["participant_id"] == "principal-1"
    assert batch["role"] == "principal"
    assert batch["samples"][0]["participant_id"] == "principal-1"
    assert batch["samples"][0]["role"] == "principal"
    assert batch["samples"][0]["rtt_ms"] == 42.0


def test_quality_snapshot_route_is_researcher_only(
    study1_client, token_manager, memory_service
):
    result = memory_service.create_session("quality-route")
    session_id = result["session"]["session_id"]
    researcher_token = token_manager.issue_researcher()

    response = study1_client.get(
        f"/api/study1/sessions/{session_id}/quality",
        headers={"Authorization": f"Bearer {researcher_token}"},
    )

    assert response.status_code == 200
    assert response.get_json()["components"]["asr"]["status"] == "unknown"
