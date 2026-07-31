from __future__ import annotations

from sqlalchemy import inspect


def test_agent_turn_is_created_before_provider_attempt(repository):
    turn = repository.begin_agent_turn(
        {
            "turn_id": "turn-1",
            "session_id": "session-1",
            "runtime_id": "runtime-1",
            "phase_version": 5,
            "turn_kind": "llm_response",
            "context_event_ids": ["utterance-1", "utterance-2"],
            "authorized_snapshot": {"facts": ["f1"]},
        }
    )

    assert turn.status == "started"
    assert turn.context_event_ids == ["utterance-1", "utterance-2"]


def test_schema_migration_creates_v2_tables_idempotently(repository):
    from media_service.app.schema_migrations import run_media_schema_migrations

    first = run_media_schema_migrations(repository.database)
    second = run_media_schema_migrations(repository.database)
    table_names = set(inspect(repository.database.engine).get_table_names())

    assert first.schema_version == "study1-media-v2"
    assert second.schema_version == "study1-media-v2"
    assert {
        "media_configs",
        "phase_spans",
        "agent_turns",
        "rtc_metrics",
        "component_health",
        "recording_tracks",
        "summary_attempts",
    } <= table_names
