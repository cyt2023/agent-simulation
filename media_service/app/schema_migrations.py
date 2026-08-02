from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import inspect

from .db import Database
from .models import Base


MEDIA_SCHEMA_VERSION = "study1-media-v2"
V2_TABLES = frozenset(
    {
        "media_configs",
        "phase_spans",
        "agent_turns",
        "rtc_metrics",
        "component_health",
        "recording_tracks",
        "summary_attempts",
    }
)


@dataclass(frozen=True)
class MediaSchemaMigrationResult:
    schema_version: str
    table_names: tuple[str, ...]


def run_media_schema_migrations(database: Database) -> MediaSchemaMigrationResult:
    Base.metadata.create_all(database.engine)
    table_names = tuple(sorted(inspect(database.engine).get_table_names()))
    return MediaSchemaMigrationResult(
        schema_version=MEDIA_SCHEMA_VERSION,
        table_names=table_names,
    )
