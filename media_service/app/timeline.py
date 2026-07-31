from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time


@dataclass(frozen=True)
class RoomClock:
    clock_id: str
    origin_utc: datetime
    origin_monotonic_ms: int

    @classmethod
    def start(
        cls,
        session_id: str,
        *,
        origin_utc: datetime | None = None,
        origin_monotonic_ms: int | None = None,
    ) -> "RoomClock":
        return cls(
            clock_id=f"room-clock-{session_id}",
            origin_utc=origin_utc or datetime.now(timezone.utc),
            origin_monotonic_ms=(
                origin_monotonic_ms
                if origin_monotonic_ms is not None
                else round(time.monotonic() * 1000)
            ),
        )

    @classmethod
    def from_snapshot(cls, payload: dict) -> "RoomClock":
        origin = datetime.fromisoformat(
            str(payload["origin_utc"]).replace("Z", "+00:00")
        )
        return cls(
            clock_id=str(payload["clock_id"]),
            origin_utc=origin,
            origin_monotonic_ms=int(payload["origin_monotonic_ms"]),
        )

    def now_room_ms(self, *, monotonic_ms: int | None = None) -> int:
        observed = (
            monotonic_ms
            if monotonic_ms is not None
            else round(time.monotonic() * 1000)
        )
        return max(0, observed - self.origin_monotonic_ms)

    def to_utc(self, room_relative_ms: int) -> datetime:
        return self.origin_utc + timedelta(milliseconds=room_relative_ms)

    def snapshot(self) -> dict:
        return {
            "clock_id": self.clock_id,
            "origin_utc": _format_utc(self.origin_utc),
            "origin_monotonic_ms": self.origin_monotonic_ms,
        }


def _format_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def recording_track_manifest(row) -> dict:
    return {
        "recording_id": row.track_id,
        "track_id": row.track_id,
        "runtime_id": row.runtime_id,
        "participant_id": row.participant_id,
        "role": row.role,
        "room_name": row.room_name,
        "clock_id": row.clock_id,
        "room_start_ms": row.room_start_ms,
        "room_end_ms": row.room_end_ms,
        "started_at_utc": _format_utc(row.started_at),
        "ended_at_utc": _format_utc(row.ended_at),
        "duration_ms": row.duration_ms,
        "size_bytes": row.size_bytes,
        "checksum": row.checksum,
        "content_type": row.content_type,
        "codec": row.codec,
        "sample_rate_hz": row.sample_rate_hz,
        "storage_uri": row.storage_uri,
        "consent_scope": row.consent_scope,
        "file_status": row.status,
    }
