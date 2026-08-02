def _event(sequence_no, event_type, observed_ms, payload=None):
    return {
        "sequence_no": sequence_no,
        "event_type": event_type,
        "observed_at_ms": observed_ms,
        "payload": payload or {},
    }


def _visit():
    return {
        "visit_id": "visit-1",
        "session_id": "session-1",
        "participant_id": "principal-1",
        "role": "principal",
    }


def test_hidden_or_stale_heartbeat_time_is_not_active():
    from study1.review_telemetry import ReviewTelemetryAccumulator

    accumulator = ReviewTelemetryAccumulator({})
    accumulator.record_batch(
        _visit(),
        [
            _event(1, "enter", 1_000),
            _event(2, "visibility", 2_000, {"state": "hidden"}),
            _event(3, "heartbeat", 22_000),
            _event(4, "visibility", 23_000, {"state": "visible"}),
            _event(5, "heartbeat", 50_000),
        ],
    )

    assert accumulator.summary("visit-1").active_seconds == 0


def test_duplicate_sequence_is_idempotent():
    from study1.review_telemetry import ReviewTelemetryAccumulator

    accumulator = ReviewTelemetryAccumulator({})
    heartbeat = _event(2, "heartbeat", 6_000)

    accumulator.record_batch(_visit(), [_event(1, "enter", 1_000), heartbeat])
    accumulator.record_batch(_visit(), [heartbeat])

    assert accumulator.summary("visit-1").active_seconds == 5
    assert accumulator.summary("visit-1").event_count == 2


def test_review_event_batch_route_sets_minimum_review_readiness(study1_client, token_manager, memory_service):
    result = memory_service.create_session("review-telemetry", minimum_review_seconds=5)
    session_id = result["session"]["session_id"]
    principal = next(invite for invite in result["invites"] if invite["role"] == "principal")
    snapshot = memory_service.repository.sessions[session_id]
    snapshot["phase"] = "REVIEW"
    snapshot["completion"]["delegation_expectation:principal"] = True

    token = token_manager.issue_participant(
        session_id,
        principal["participant_id"],
        "principal",
    )
    response = study1_client.post(
        f"/api/study1/sessions/{session_id}/review-events/batch",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "visit_id": "visit-route",
            "events": [
                _event(1, "enter", 1_000),
                _event(2, "heartbeat", 6_000),
            ],
        },
    )

    assert response.status_code == 202
    body = response.get_json()
    assert body["summary"]["active_seconds"] == 5
    assert snapshot["completion"]["review_reading_recorded:principal"] is True
    assert snapshot["completion"]["minimum_review_time_met:principal"] is True
