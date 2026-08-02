"""Server-side Review telemetry accumulation for Study 1."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping


MAX_HEARTBEAT_GAP_MS = 15_000


@dataclass(frozen=True)
class ReviewTelemetrySummary:
    visit_id: str
    active_seconds: int
    event_count: int
    duplicate_count: int
    max_scroll_depth: float
    transcript_expanded: bool
    transcript_expand_count: int
    visible_segments: list[str]
    replay_ranges: list[dict[str, int]]

    def public_dict(self) -> dict[str, Any]:
        return {
            "visit_id": self.visit_id,
            "active_seconds": self.active_seconds,
            "event_count": self.event_count,
            "duplicate_count": self.duplicate_count,
            "max_scroll_depth": self.max_scroll_depth,
            "transcript_expanded": self.transcript_expanded,
            "transcript_expand_count": self.transcript_expand_count,
            "visible_segments": list(self.visible_segments),
            "replay_ranges": copy.deepcopy(self.replay_ranges),
        }


class ReviewTelemetryAccumulator:
    """Mutates a JSON-serializable telemetry state dictionary in place."""

    def __init__(self, state: dict[str, Any]):
        self.state = state
        self.state.setdefault("visits", {})

    def record_batch(
        self,
        visit: Mapping[str, Any],
        events: list[Mapping[str, Any]],
        *,
        received_at_ms: int | None = None,
    ) -> ReviewTelemetrySummary:
        visit_id = str(visit.get("visit_id") or "").strip()
        if not visit_id:
            raise ValueError("visit_id is required")
        record = self._visit_record(visit)
        for raw_event in sorted(events, key=lambda item: int(item.get("sequence_no") or 0)):
            sequence_no = int(raw_event.get("sequence_no") or 0)
            if sequence_no <= 0:
                continue
            sequence_key = str(sequence_no)
            if sequence_key in record["seen_sequences"]:
                record["duplicate_count"] += 1
                continue
            record["seen_sequences"][sequence_key] = True
            event_type = str(raw_event.get("event_type") or "").strip()
            observed_at_ms = int(
                raw_event.get("observed_at_ms")
                if raw_event.get("observed_at_ms") is not None
                else received_at_ms or 0
            )
            payload = raw_event.get("payload") if isinstance(raw_event.get("payload"), dict) else {}
            self._apply_event(record, event_type, observed_at_ms, payload)
        return self.summary(visit_id)

    def summary(self, visit_id: str) -> ReviewTelemetrySummary:
        record = self.state["visits"].get(visit_id)
        if not record:
            return ReviewTelemetrySummary(
                visit_id=visit_id,
                active_seconds=0,
                event_count=0,
                duplicate_count=0,
                max_scroll_depth=0.0,
                transcript_expanded=False,
                transcript_expand_count=0,
                visible_segments=[],
                replay_ranges=[],
            )
        return ReviewTelemetrySummary(
            visit_id=visit_id,
            active_seconds=int(record.get("active_ms") or 0) // 1000,
            event_count=len(record.get("seen_sequences") or {}),
            duplicate_count=int(record.get("duplicate_count") or 0),
            max_scroll_depth=float(record.get("max_scroll_depth") or 0.0),
            transcript_expanded=bool(record.get("transcript_expanded")),
            transcript_expand_count=int(record.get("transcript_expand_count") or 0),
            visible_segments=sorted(record.get("visible_segments") or []),
            replay_ranges=copy.deepcopy(record.get("replay_ranges") or []),
        )

    def _visit_record(self, visit: Mapping[str, Any]) -> dict[str, Any]:
        visit_id = str(visit.get("visit_id") or "")
        visits = self.state.setdefault("visits", {})
        record = visits.setdefault(
            visit_id,
            {
                "visit_id": visit_id,
                "session_id": str(visit.get("session_id") or ""),
                "participant_id": str(visit.get("participant_id") or ""),
                "role": str(visit.get("role") or ""),
                "visible": False,
                "focused": False,
                "last_heartbeat_ms": None,
                "active_ms": 0,
                "seen_sequences": {},
                "duplicate_count": 0,
                "max_scroll_depth": 0.0,
                "transcript_expanded": False,
                "transcript_expand_count": 0,
                "visible_segments": [],
                "replay_ranges": [],
            },
        )
        return record

    def _apply_event(
        self, record: dict[str, Any], event_type: str, observed_at_ms: int, payload: dict[str, Any]
    ) -> None:
        if event_type == "enter":
            record["visible"] = True
            record["focused"] = True
            record["last_heartbeat_ms"] = observed_at_ms
            return
        if event_type == "leave":
            record["visible"] = False
            record["focused"] = False
            record["last_heartbeat_ms"] = None
            return
        if event_type == "visibility":
            record["visible"] = payload.get("state") == "visible"
            record["last_heartbeat_ms"] = observed_at_ms if record["visible"] else None
            return
        if event_type == "focus":
            record["focused"] = payload.get("focused") is not False
            record["last_heartbeat_ms"] = observed_at_ms if record["focused"] else None
            return
        if event_type == "heartbeat":
            prior = record.get("last_heartbeat_ms")
            if record.get("visible") and record.get("focused") and prior is not None:
                gap = max(0, observed_at_ms - int(prior))
                if gap <= MAX_HEARTBEAT_GAP_MS:
                    record["active_ms"] = int(record.get("active_ms") or 0) + gap
            record["last_heartbeat_ms"] = (
                observed_at_ms
                if record.get("visible") and record.get("focused")
                else None
            )
            return
        if event_type == "scroll":
            depth = max(0.0, min(1.0, float(payload.get("max_depth") or 0.0)))
            record["max_scroll_depth"] = max(
                float(record.get("max_scroll_depth") or 0.0), depth
            )
            for segment in payload.get("visible_segments") or []:
                _append_unique(record["visible_segments"], str(segment)[:64])
            return
        if event_type == "transcript_toggle":
            expanded = payload.get("expanded") is True
            record["transcript_expanded"] = expanded
            if expanded:
                record["transcript_expand_count"] = (
                    int(record.get("transcript_expand_count") or 0) + 1
                )
            return
        if event_type == "segment_visible":
            _append_unique(
                record["visible_segments"],
                str(payload.get("segment_id") or "")[:64],
            )
            return
        if event_type == "replay_range":
            start_ms = max(0, int(payload.get("start_ms") or 0))
            end_ms = max(start_ms, int(payload.get("end_ms") or start_ms))
            record["replay_ranges"].append({"start_ms": start_ms, "end_ms": end_ms})


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
