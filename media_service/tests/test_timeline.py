from __future__ import annotations

from datetime import datetime, timezone

from media_service.app.timeline import RoomClock


def test_room_clock_converts_room_offsets_to_utc():
    origin = datetime(2026, 7, 31, 0, 0, 0, tzinfo=timezone.utc)
    clock = RoomClock(
        clock_id="room-clock-session-1",
        origin_utc=origin,
        origin_monotonic_ms=1_000,
    )

    assert clock.now_room_ms(monotonic_ms=91_000) == 90_000
    assert clock.to_utc(90_000).isoformat().replace("+00:00", "Z") == (
        "2026-07-31T00:01:30Z"
    )
    assert clock.snapshot() == {
        "clock_id": "room-clock-session-1",
        "origin_utc": "2026-07-31T00:00:00Z",
        "origin_monotonic_ms": 1_000,
    }
