from __future__ import annotations

from datetime import datetime, timezone
from statistics import median

from .repository import MediaRepository


COMPONENTS = ("recorder", "asr", "llm", "tts", "proxy")


class HealthService:
    def __init__(self, repository: MediaRepository):
        self.repository = repository

    def record_success(
        self,
        component: str,
        *,
        latency_ms: float | None = None,
        payload: dict | None = None,
    ):
        return self.repository.record_component_health(
            component=component,
            status="healthy",
            latency_ms=latency_ms,
            error_code=None,
            payload=payload or {},
        )

    def record_failure(
        self,
        component: str,
        error_code: str,
        *,
        latency_ms: float | None = None,
        payload: dict | None = None,
    ):
        return self.repository.record_component_health(
            component=component,
            status="failed",
            latency_ms=latency_ms,
            error_code=error_code,
            payload=payload or {},
        )

    def snapshot(self, *, now: datetime | None = None) -> dict[str, dict]:
        current = now or datetime.now(timezone.utc)
        rows_by_component: dict[str, list] = {component: [] for component in COMPONENTS}
        for row in self.repository.list_component_health():
            if row.component in rows_by_component:
                rows_by_component[row.component].append(row)
        return {
            component: _component_snapshot(rows, now=current)
            for component, rows in rows_by_component.items()
        }


def _component_snapshot(rows: list, *, now: datetime) -> dict:
    if not rows:
        return {
            "status": "unknown",
            "last_success_at": None,
            "last_error_code": None,
            "p50_latency_ms": None,
            "p95_latency_ms": None,
        }
    latest = rows[-1]
    successes = [row for row in rows if row.status in {"healthy", "ready", "success"}]
    latencies = [
        float(row.latency_ms)
        for row in successes
        if row.latency_ms is not None
    ]
    last_success = successes[-1].observed_at if successes else None
    status = str(latest.status or "unknown")
    if status in {"ready", "success"}:
        status = "healthy"
    if status not in {"unknown", "healthy", "degraded", "failed"}:
        status = "unknown"
    return {
        "status": status,
        "last_success_at": _format_utc(last_success),
        "last_error_code": latest.error_code,
        "p50_latency_ms": _percentile(latencies, 50),
        "p95_latency_ms": _percentile(latencies, 95),
    }


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if percentile == 50:
        return median(ordered)
    index = min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1)))
    return ordered[index]


def _format_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
