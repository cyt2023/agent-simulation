from __future__ import annotations

import copy

from services.db import Base


FORMAL_TABLES = {
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
}


def test_audio_completion_schema_is_additive_and_registered():
    import study1.models  # noqa: F401

    assert FORMAL_TABLES <= {table.name for table in Base.metadata.tables.values()}


def test_definition_tables_use_logical_id_and_version_unique_keys():
    from study1.models import (
        Study1InstrumentDefinitionRow,
        Study1InstrumentItemRow,
        Study1TaskDefinitionRow,
        Study1TaskFactRow,
    )

    def unique_columns(model):
        return {
            tuple(column.name for column in constraint.columns)
            for constraint in model.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }

    assert ("task_definition_id", "task_version") in unique_columns(
        Study1TaskDefinitionRow
    )
    assert ("task_definition_id", "task_version", "fact_id") in unique_columns(
        Study1TaskFactRow
    )
    assert (
        "instrument_definition_id",
        "instrument_version",
    ) in unique_columns(Study1InstrumentDefinitionRow)
    assert (
        "instrument_definition_id",
        "instrument_version",
        "item_id",
    ) in unique_columns(Study1InstrumentItemRow)


def test_legacy_migration_marks_only_unversioned_study1_payloads():
    from study1.schema_migrations import mark_legacy_payload

    original = {
        "experiment_type": "study1",
        "session_id": "legacy-session",
        "phase": "REVIEW",
    }
    untouched = copy.deepcopy(original)

    migrated, changed = mark_legacy_payload(original)

    assert changed is True
    assert original == untouched
    assert migrated["protocol_mode"] == "legacy_protocol"
    assert migrated["formal_certifiable"] is False
    assert migrated["legacy_migrated_at"]


def test_legacy_migration_never_downgrades_formal_or_non_study1_payloads():
    from study1.schema_migrations import mark_legacy_payload

    formal = {
        "experiment_type": "study1",
        "protocol_mode": "formal_v2",
        "formal_certifiable": True,
    }
    legacy_platform = {"experiment_type": "hidden_profile"}

    assert mark_legacy_payload(formal) == (formal, False)
    assert mark_legacy_payload(legacy_platform) == (legacy_platform, False)
