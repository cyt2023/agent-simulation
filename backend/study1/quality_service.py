"""Study 1 media quality aggregation from authenticated evidence."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from statistics import median
from typing import Any


RTC_STALE_AFTER_SECONDS = 120


def normalize_rtc_metric(
    session_id: str,
    actor: dict[str, Any],
    payload: dict[str, Any],
    received_at: datetime,
) -> dict[str, Any]:
    observed_at = _parse_time(payload.get("observed_at")) or received_at
    return {
        "session_id": session_id,
        "participant_id": str(actor.get("participant_id") or ""),
        "role": str(actor.get("role") or ""),
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "rtt_ms": _number_or_none(payload.get("rtt_ms")),
        "jitter_ms": _number_or_none(payload.get("jitter_ms")),
        "packet_loss": _number_or_none(payload.get("packet_loss")),
        "bitrate_kbps": _number_or_none(payload.get("bitrate_kbps")),
        "connection_state": str(payload.get("connection_state") or "unknown")[:64],
        "metadata": copy.deepcopy(payload.get("metadata") or {}),
    }


def build_quality_snapshot(
    *,
    session_id: str,
    data: dict[str, Any],
    media_status: dict[str, Any] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    samples = _latest_rtc_samples(data.get("events") or [])
    fresh = []
    stale = []
    for sample in samples:
        observed_at = _parse_time(sample.get("observed_at"))
        if observed_at is None:
            stale.append(sample)
            continue
        age = (current - observed_at).total_seconds()
        if age <= RTC_STALE_AFTER_SECONDS:
            fresh.append(sample)
        else:
            stale.append(sample)

    rtc_status = "unknown"
    if fresh:
        rtc_status = (
            "degraded"
            if any(
                (sample.get("packet_loss") or 0) > 0.05
                or str(sample.get("connection_state") or "") not in {"connected", "stable"}
                for sample in fresh
            )
            else "healthy"
        )

    rtts = [sample["rtt_ms"] for sample in fresh if sample.get("rtt_ms") is not None]
    media = copy.deepcopy(media_status or {})
    return {
        "session_id": session_id,
        "rtc": {
            "status": rtc_status,
            "fresh_participant_count": len(fresh),
            "stale_participant_count": len(stale),
            "p50_rtt_ms": _percentile(rtts, 50),
            "p95_rtt_ms": _percentile(rtts, 95),
            "last_samples": fresh,
        },
        "components": _component_snapshot(media),
        "media_service": media,
        "generated_at": current.isoformat().replace("+00:00", "Z"),
    }


def _latest_rtc_samples(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for event in events:
        payload = event.get("payload") or {}
        if payload.get("ui_event_type") != "rtc_metric_sample":
            continue
        participant_id = str(event.get("participant_id") or payload.get("participant_id") or "")
        if not participant_id:
            continue
        sample = copy.deepcopy(payload)
        sample["participant_id"] = participant_id
        sample["role"] = event.get("role") or sample.get("role")
        sample.setdefault("observed_at", event.get("occurred_at"))
        latest[participant_id] = sample
    return list(latest.values())


def _component_snapshot(media_status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_components = media_status.get("components") or {}
    result: dict[str, dict[str, Any]] = {}
    for component in ("recorder", "asr", "llm", "tts", "proxy"):
        raw = raw_components.get(component) or media_status.get(component) or {}
        status = str(raw.get("status") or "unknown")
        if status == "ready":
            status = "healthy"
        result[component] = {
            "status": status if status in {"unknown", "healthy", "degraded", "failed"} else "unknown",
            "last_success_at": raw.get("last_success_at"),
            "last_error_code": raw.get("last_error_code"),
            "p50_latency_ms": raw.get("p50_latency_ms"),
            "p95_latency_ms": raw.get("p95_latency_ms"),
        }
    return result


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if percentile == 50:
        return median(ordered)
    index = min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1)))
    return ordered[index]
