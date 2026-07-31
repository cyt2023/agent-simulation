"""Deterministic replay-window generation for Study 1 interview review."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime
from typing import Any


class ReplayValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def build_replay_plan(
    *,
    session_id: str,
    markers: list[dict[str, Any]],
    existing_count: int,
    created_by: str,
    context_seconds: int,
    created_at: datetime,
) -> dict[str, Any]:
    if context_seconds < 0 or context_seconds > 300:
        raise ReplayValidationError(
            "INVALID_REPLAY_CONTEXT", "context_seconds must be between 0 and 300"
        )
    if not markers:
        raise ReplayValidationError(
            "REPLAY_MARKERS_REQUIRED", "At least one marker is required"
        )

    context_ms = context_seconds * 1000
    windows: list[dict[str, Any]] = []
    for marker in sorted(markers, key=lambda item: (item["start_ms"], item["end_ms"])):
        start_ms = max(0, int(marker["start_ms"]) - context_ms)
        end_ms = int(marker["end_ms"]) + context_ms
        windows.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "marker_ids": [marker["marker_id"]],
                "segment_ids": list(marker.get("segment_ids") or []),
                "recording_ids": list(marker.get("recording_ids") or []),
            }
        )

    merged: list[dict[str, Any]] = []
    for window in windows:
        if not merged or window["start_ms"] > merged[-1]["end_ms"]:
            merged.append(copy.deepcopy(window))
            continue
        current = merged[-1]
        current["end_ms"] = max(current["end_ms"], window["end_ms"])
        current["marker_ids"].extend(window["marker_ids"])
        current["segment_ids"] = _dedupe(
            current["segment_ids"] + window["segment_ids"]
        )
        current["recording_ids"] = _dedupe(
            current["recording_ids"] + window["recording_ids"]
        )

    items = []
    for index, window in enumerate(merged, start=1):
        items.append(
            {
                "item_id": str(uuid.uuid4()),
                "order_index": index,
                "start_ms": window["start_ms"],
                "end_ms": window["end_ms"],
                "start_second": window["start_ms"] // 1000,
                "end_second": _ceil_second(window["end_ms"]),
                "marker_ids": window["marker_ids"],
                "segment_ids": window["segment_ids"],
                "recording_ids": window["recording_ids"],
            }
        )

    return {
        "replay_plan_id": str(uuid.uuid4()),
        "session_id": session_id,
        "version": str(existing_count + 1),
        "context_seconds": context_seconds,
        "source_marker_ids": [marker["marker_id"] for marker in markers],
        "items": items,
        "created_by": created_by,
        "created_at": created_at,
        "generator_version": "deterministic-replay-v1",
        "metadata": {"selection": "fixed_context_window_merge"},
    }


def _ceil_second(value_ms: int) -> int:
    return (value_ms + 999) // 1000


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
