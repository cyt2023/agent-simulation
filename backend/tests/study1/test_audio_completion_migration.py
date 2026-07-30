from __future__ import annotations

import copy
from datetime import datetime, timezone

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from services.db import ResearchSessionRow, get_app_schema
from study1.models import (
    Study1EventRow,
    Study1SchemaVersionRow,
    Study1SubmissionRow,
)


MIGRATION_REVISION = "20260729_01_audio_completion_schema"


def _now():
    return datetime.now(timezone.utc)


def _seed_legacy_data(engine):
    sessions = [
        ResearchSessionRow(
            session_id="legacy-study1",
            session_name="Legacy Study 1",
            payload={
                "experiment_type": "study1",
                "session_id": "legacy-study1",
                "phase": "REVIEW",
            },
            updated_at=_now(),
        ),
        ResearchSessionRow(
            session_id="formal-study1",
            session_name="Formal Study 1",
            payload={
                "experiment_type": "study1",
                "session_id": "formal-study1",
                "protocol_mode": "formal_v2",
                "formal_certifiable": True,
            },
            updated_at=_now(),
        ),
        ResearchSessionRow(
            session_id="legacy-platform",
            session_name="Legacy platform",
            payload={"experiment_type": "hidden_profile", "phase": "discussion"},
            updated_at=_now(),
        ),
    ]
    submission = Study1SubmissionRow(
        submission_id="submission-before-migration",
        session_id="legacy-study1",
        participant_id="participant-1",
        role="principal",
        phase="PRE_VOTE",
        instrument_version="v1",
        payload={"_submission_type": "pre_vote", "decision": "candidate-a"},
        submitted_at=_now(),
        server_timestamp=_now(),
        client_timestamp=None,
        locked=True,
        previous_submission_id=None,
        revision_operator=None,
        revision_reason=None,
    )
    event = Study1EventRow(
        event_id="event-before-migration",
        session_id="legacy-study1",
        participant_id="participant-1",
        role="principal",
        phase="PRE_VOTE",
        phase_version=2,
        event_type="submission_created",
        occurred_at=_now(),
        payload={"submission_id": submission.submission_id},
        idempotency_key=None,
    )
    with Session(engine) as db:
        db.add_all([*sessions, submission, event])
        db.commit()


def test_audio_completion_migration_is_versioned_additive_and_idempotent(
    study1_sqlite_engine,
):
    from study1.schema_migrations import run_study1_migrations

    _seed_legacy_data(study1_sqlite_engine)
    with Session(study1_sqlite_engine) as db:
        submissions_before = copy.deepcopy(db.scalars(select(Study1SubmissionRow)).all())
        events_before = copy.deepcopy(db.scalars(select(Study1EventRow)).all())

    first = run_study1_migrations(study1_sqlite_engine)
    second = run_study1_migrations(study1_sqlite_engine)

    assert first == [MIGRATION_REVISION]
    assert second == []
    table_names = set(
        inspect(study1_sqlite_engine).get_table_names(schema=get_app_schema())
    )
    assert {
        "study1_schema_versions",
        "study1_task_definitions",
        "study1_task_facts",
        "study1_role_assignments",
        "study1_fact_assignments",
        "study1_protocol_snapshots",
        "study1_decisions",
        "study1_shared_artifacts",
        "study1_shared_revisions",
        "study1_shared_confirmations",
        "study1_instrument_definitions",
        "study1_instrument_items",
        "study1_instrument_responses",
    } <= table_names

    with Session(study1_sqlite_engine) as db:
        revisions = db.scalars(select(Study1SchemaVersionRow)).all()
        assert [row.revision for row in revisions] == [MIGRATION_REVISION]
        assert db.scalar(select(func.count()).select_from(Study1SchemaVersionRow)) == 1

        snapshots = {
            row.session_id: dict(row.payload)
            for row in db.scalars(select(ResearchSessionRow)).all()
        }
        assert snapshots["legacy-study1"]["protocol_mode"] == "legacy_protocol"
        assert snapshots["legacy-study1"]["formal_certifiable"] is False
        assert snapshots["legacy-study1"]["legacy_migrated_at"]
        assert snapshots["formal-study1"]["protocol_mode"] == "formal_v2"
        assert snapshots["formal-study1"]["formal_certifiable"] is True
        assert "protocol_mode" not in snapshots["legacy-platform"]

        submissions_after = db.scalars(select(Study1SubmissionRow)).all()
        events_after = db.scalars(select(Study1EventRow)).all()
        assert [row.submission_id for row in submissions_after] == [
            row.submission_id for row in submissions_before
        ]
        assert [dict(row.payload) for row in submissions_after] == [
            dict(row.payload) for row in submissions_before
        ]
        assert [row.event_id for row in events_after] == [
            row.event_id for row in events_before
        ]
        assert [dict(row.payload) for row in events_after] == [
            dict(row.payload) for row in events_before
        ]
