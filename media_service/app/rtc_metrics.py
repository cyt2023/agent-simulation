from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any

from .repository import MediaRepository


class RtcMetricsService:
    def __init__(self, repository: MediaRepository):
        self.repository = repository

    def record_batch(
        self,
        *,
        session_id: str,
        phase_version: int,
        participant_id: str,
        role: str,
        samples: list[dict[str, Any]],
    ) -> dict:
        for sample in samples:
            normalized = normalize_rtc_sample(sample)
            self.repository.record_rtc_metric(
                session_id=session_id,
                participant_id=participant_id,
                role=role,
                observed_at=normalized["observed_at"],
                payload={
                    key: value
                    for key, value in normalized.items()
                    if key != "observed_at"
                },
            )
        snapshot = self.snapshot(session_id)
        self.repository.enqueue_event(
            session_id,
            phase_version,
            "RTC_METRIC_BATCH",
            {
                "participant_id": participant_id,
                "role": role,
                "sample_count": len(samples),
                "rtc_status": snapshot["status"],
            },
        )
        return snapshot

    def snapshot(self, session_id: str) -> dict:
        rows = self.repository.list_session_rtc_metrics(session_id)
        if not rows:
            return {
                "status": "unknown",
                "sample_count": 0,
                "participant_count": 0,
                "p50_rtt_ms": None,
                "p95_rtt_ms": None,
                "last_samples": [],
            }
        samples = [
            {
                **(row.payload or {}),
                "participant_id": row.participant_id,
                "role": row.role,
                "observed_at": _format_utc(row.observed_at),
            }
            for row in rows
        ]
        rtts = [
            float(sample["rtt_ms"])
            for sample in samples
            if sample.get("rtt_ms") is not None
        ]
        degraded = any(
            (sample.get("packet_loss") or 0) > 0.05
            or str(sample.get("connection_state") or "unknown")
            not in {"connected", "stable"}
            for sample in samples
        )
        return {
            "status": "degraded" if degraded else "healthy",
            "sample_count": len(samples),
            "participant_count": len({row.participant_id for row in rows}),
            "p50_rtt_ms": _percentile(rtts, 50),
            "p95_rtt_ms": _percentile(rtts, 95),
            "last_samples": _latest_by_participant(samples),
        }


def normalize_rtc_sample(sample: dict[str, Any]) -> dict:
    observed_at = _parse_time(sample.get("observed_at")) or datetime.now(timezone.utc)
    return {
        "observed_at": observed_at,
        "rtt_ms": _number_or_none(sample.get("rtt_ms")),
        "jitter_ms": _number_or_none(sample.get("jitter_ms")),
        "packet_loss": _number_or_none(sample.get("packet_loss")),
        "bitrate_kbps": _number_or_none(sample.get("bitrate_kbps")),
        "connection_state": str(sample.get("connection_state") or "unknown")[:64],
        "metadata": dict(sample.get("metadata") or {}),
    }


def _latest_by_participant(samples: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for sample in samples:
        latest[str(sample.get("participant_id") or "")] = sample
    return list(latest.values())


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


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if percentile == 50:
        return median(ordered)
    index = min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1)))
    return ordered[index]
