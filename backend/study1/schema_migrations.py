"""Versioned additive migrations for the Study 1 audio-completion protocol."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from services.db import ResearchSessionRow, get_app_schema
from .models import (
    Study1DecisionRow,
    Study1FactAssignmentRow,
    Study1InstrumentDefinitionRow,
    Study1InstrumentItemRow,
    Study1InstrumentResponseRow,
    Study1MarkerRow,
    Study1ProtocolSnapshotRow,
    Study1ReplayPlanRow,
    Study1RoleAssignmentRow,
    Study1SchemaVersionRow,
    Study1SharedArtifactRow,
    Study1SharedConfirmationRow,
    Study1SharedRevisionRow,
    Study1TaskDefinitionRow,
    Study1TaskFactRow,
)


AUDIO_COMPLETION_REVISION = "20260729_01_audio_completion_schema"
STUDY1_ADDITIVE_TABLES = (
    Study1SchemaVersionRow.__table__,
    Study1TaskDefinitionRow.__table__,
    Study1TaskFactRow.__table__,
    Study1RoleAssignmentRow.__table__,
    Study1FactAssignmentRow.__table__,
    Study1ProtocolSnapshotRow.__table__,
    Study1DecisionRow.__table__,
    Study1SharedArtifactRow.__table__,
    Study1SharedRevisionRow.__table__,
    Study1SharedConfirmationRow.__table__,
    Study1InstrumentDefinitionRow.__table__,
    Study1InstrumentItemRow.__table__,
    Study1InstrumentResponseRow.__table__,
    Study1MarkerRow.__table__,
    Study1ReplayPlanRow.__table__,
)
STUDY1_ADDITIVE_TABLE_NAMES = frozenset(
    table.name for table in STUDY1_ADDITIVE_TABLES
)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def mark_legacy_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return an upgraded copy without changing already-versioned sessions."""

    if payload.get("experiment_type") != "study1" or payload.get("protocol_mode"):
        return payload, False
    migrated = copy.deepcopy(payload)
    migrated["protocol_mode"] = "legacy_protocol"
    migrated["formal_certifiable"] = False
    migrated["legacy_migrated_at"] = _utc_iso()
    return migrated, True


def mark_existing_study1_sessions_legacy(session_factory) -> int:
    """Mark pre-V2 Study 1 snapshots once; never rewrite formal snapshots."""

    with session_factory() as db:
        changed_count = _mark_existing_study1_sessions_legacy(db)
        if changed_count:
            db.commit()
    return changed_count


def _mark_existing_study1_sessions_legacy(db: Session) -> int:
    changed_count = 0
    rows = db.scalars(select(ResearchSessionRow)).all()
    for row in rows:
        migrated, changed = mark_legacy_payload(dict(row.payload or {}))
        if not changed:
            continue
        row.payload = migrated
        row.updated_at = datetime.now(timezone.utc)
        changed_count += 1
    return changed_count


def run_study1_migrations(engine) -> list[str]:
    """Apply pending Study 1 revisions and return the revisions applied now."""

    Study1SchemaVersionRow.__table__.create(bind=engine, checkfirst=True)
    applied: list[str] = []
    with engine.begin() as connection:
        with Session(bind=connection) as db:
            if db.get(Study1SchemaVersionRow, AUDIO_COMPLETION_REVISION):
                return applied
            for table in STUDY1_ADDITIVE_TABLES[1:]:
                table.create(bind=connection, checkfirst=True)
            if inspect(connection).has_table(
                ResearchSessionRow.__tablename__, schema=get_app_schema()
            ):
                _mark_existing_study1_sessions_legacy(db)
            db.add(
                Study1SchemaVersionRow(
                    revision=AUDIO_COMPLETION_REVISION,
                    applied_at=datetime.now(timezone.utc),
                )
            )
            db.flush()
            applied.append(AUDIO_COMPLETION_REVISION)
    return applied
