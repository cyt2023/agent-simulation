"""Canonical, versioned Study 1 protocol configuration.

The protocol snapshot is deliberately represented as plain JSON-compatible data.
That makes the value safe to persist in both the SQL and in-memory adapters and
keeps checksum calculation independent from SQLAlchemy model instances.
"""

from __future__ import annotations

import copy
import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import PHASE_ORDER, Study1Phase


class ProtocolConfigError(ValueError):
    """Raised when a formal protocol cannot be normalized or verified."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ProtocolConfigV2(dict[str, Any]):
    """JSON-compatible marker type for a normalized formal configuration."""


def _non_empty(value: Any, field: str, default: str | None = None) -> str:
    clean = str(value if value is not None else (default or "")).strip()
    if not clean:
        raise ProtocolConfigError("FIELD_REQUIRED", f"{field} is required")
    return clean


def _validate_timezone(value: Any) -> str:
    timezone_name = _non_empty(value, "laboratory_timezone", "UTC")
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ProtocolConfigError(
            "INVALID_TIMEZONE", "laboratory_timezone must be an IANA timezone"
        ) from error
    return timezone_name


def _phase_durations(value: Any, *, required: bool) -> dict[str, int]:
    if value is None:
        if required:
            raise ProtocolConfigError(
                "MISSING_PHASE_DURATIONS",
                "phase_durations_seconds must include every Study 1 phase",
            )
        value = {}
    if not isinstance(value, Mapping):
        raise ProtocolConfigError(
            "INVALID_PHASE_DURATIONS", "phase_durations_seconds must be an object"
        )
    known = {phase.value for phase in PHASE_ORDER}
    unknown = sorted(set(value) - known)
    if unknown:
        raise ProtocolConfigError(
            "INVALID_PHASE_DURATIONS", f"Unknown phase duration: {unknown[0]}"
        )
    missing = [phase.value for phase in PHASE_ORDER if phase.value not in value]
    if missing and required:
        raise ProtocolConfigError(
            "MISSING_PHASE_DURATIONS",
            "Missing phase durations: " + ", ".join(missing),
        )
    result: dict[str, int] = {}
    for phase in PHASE_ORDER:
        raw = value.get(phase.value, 0)
        try:
            seconds = int(raw)
        except (TypeError, ValueError) as error:
            raise ProtocolConfigError(
                "INVALID_PHASE_DURATION",
                f"Duration for {phase.value} must be an integer",
            ) from error
        if seconds < 0 or seconds > 86_400:
            raise ProtocolConfigError(
                "INVALID_PHASE_DURATION",
                f"Duration for {phase.value} must be between 0 and 86400",
            )
        result[phase.value] = seconds
    return result


def formal_protocol_defaults(randomization_seed: str | None = None) -> dict[str, Any]:
    """Return explicit non-unknown development defaults for formal Sessions.

    Deployments should replace the build/provider identifiers through the
    environment or request payload.  The defaults are intentionally named
    rather than ``unknown`` so local Mock mode remains testable.
    """

    return {
        "protocol_version": "study1-audio-formal-v2",
        "task_version": "2.0",
        "task_instance_id": "study1-default",
        "consent_version": "study1-consent-v1",
        "instrument_catalog_version": "study1-instruments-v2",
        "instrument_catalog_checksum": "study1-instruments-v2-dev",
        "ui_schema_version": "study1-ui-v2",
        "phase_durations_seconds": {
            phase.value: 0
            for phase in PHASE_ORDER
        },
        "minimum_review_seconds": 0,
        "laboratory_timezone": "UTC",
        "recording_mode": "audio_only",
        "authority_level": "suggest",
        "proxy_provider": "mock",
        "proxy_model": "study1-proxy-v2",
        "proxy_prompt_version": "study1-proxy-neutral-v2",
        "proxy_prompt_checksum": "study1-proxy-neutral-v2-dev",
        "proxy_sampling": {"temperature": 0, "top_p": 1},
        "asr_provider": "mock",
        "asr_model": "study1-asr-v2",
        "tts_provider": "mock",
        "tts_model": "study1-tts-v2",
        "tts_voice": "neutral-en-us",
        "summary_provider": "mock",
        "summary_model": "study1-summary-v2",
        "summary_prompt_version": "study1-summary-neutral-v2",
        "summary_prompt_checksum": "study1-summary-neutral-v2-dev",
        "summary_template_version": "study1-five-section-v1",
        "summary_sampling": {"temperature": 0, "top_p": 1},
        "summary_retry_count": 1,
        "summary_failure_policy": "transcript_only",
        "transcript_access_policy": "principal_after_delegation",
        "retention_policy": {
            "review_days": 30,
            "deletion_days": 365,
            "media_disposition": "controlled_purge",
        },
        "media_access_policy": "authorized_phase_only",
        "feature_flags": {"resync_enabled": False, "video_enabled": False},
        "build_ids": {
            "frontend": "frontend-dev",
            "backend": "backend-dev",
            "media": "media-dev",
        },
        "role_assignment_mode": "fixed",
        "randomization_seed": randomization_seed or secrets.token_hex(8),
        "require_consent": False,
        "structured_instruments": True,
    }


def normalize_protocol_config_v2(value: Mapping[str, Any]) -> ProtocolConfigV2:
    """Validate and canonicalize a complete formal V2 configuration."""

    if not isinstance(value, Mapping):
        raise ProtocolConfigError("INVALID_CONFIG", "Protocol config must be an object")
    raw = copy.deepcopy(dict(value))
    durations = _phase_durations(raw.get("phase_durations_seconds"), required=True)
    recording_mode = str(raw.get("recording_mode") or "").strip().lower()
    if recording_mode != "audio_only":
        raise ProtocolConfigError(
            "AUDIO_ONLY_REQUIRED", "Study 1 protocol recording_mode must be audio_only"
        )
    authority = str(raw.get("authority_level") or "").strip()
    if authority not in {"share_only", "suggest", "agree_tentative"}:
        raise ProtocolConfigError(
            "INVALID_AUTHORITY_LEVEL",
            "authority_level must be share_only, suggest, or agree_tentative",
        )
    minimum_review = raw.get("minimum_review_seconds", 0)
    try:
        minimum_review = int(minimum_review)
    except (TypeError, ValueError) as error:
        raise ProtocolConfigError(
            "INVALID_REVIEW_DURATION", "minimum_review_seconds must be an integer"
        ) from error
    if minimum_review < 0 or minimum_review > 86_400:
        raise ProtocolConfigError(
            "INVALID_REVIEW_DURATION",
            "minimum_review_seconds must be between 0 and 86400",
        )

    feature_flags = raw.get("feature_flags")
    if not isinstance(feature_flags, Mapping):
        raise ProtocolConfigError("FEATURE_FLAGS_REQUIRED", "feature_flags is required")
    if feature_flags.get("resync_enabled") is not False:
        raise ProtocolConfigError("RESYNC_DISABLED", "Study 1 requires resync_enabled=false")
    if feature_flags.get("video_enabled") is not False:
        raise ProtocolConfigError("VIDEO_DISABLED", "Study 1 is audio-only")
    if raw.get("module_id") is not None:
        raise ProtocolConfigError(
            "MODULE_ID_NOT_ALLOWED",
            "Study 1 protocol does not permit extension module_id values",
        )

    build_ids = raw.get("build_ids")
    if not isinstance(build_ids, Mapping):
        raise ProtocolConfigError("BUILD_IDS_REQUIRED", "build_ids is required")
    clean_build_ids: dict[str, str] = {}
    for component in ("frontend", "backend", "media"):
        build = _non_empty(build_ids.get(component), f"build_ids.{component}")
        if build.lower() in {"unknown", "unset", "latest"}:
            raise ProtocolConfigError(
                "BUILD_ID_REQUIRED", f"build_ids.{component} cannot be unknown"
            )
        clean_build_ids[component] = build[:128]

    summary_failure = str(raw.get("summary_failure_policy") or "").strip()
    if summary_failure not in {"transcript_only", "terminate_session"}:
        raise ProtocolConfigError(
            "INVALID_SUMMARY_FAILURE_POLICY",
            "summary_failure_policy must be transcript_only or terminate_session",
        )
    retry_count = raw.get("summary_retry_count", 0)
    try:
        retry_count = int(retry_count)
    except (TypeError, ValueError) as error:
        raise ProtocolConfigError(
            "INVALID_SUMMARY_RETRY_COUNT", "summary_retry_count must be an integer"
        ) from error
    if retry_count < 0 or retry_count > 5:
        raise ProtocolConfigError(
            "INVALID_SUMMARY_RETRY_COUNT", "summary_retry_count must be between 0 and 5"
        )

    normalized = ProtocolConfigV2(
        {
            "protocol_version": _non_empty(
                raw.get("protocol_version"), "protocol_version", "study1-audio-formal-v2"
            )[:64],
            "task_version": _non_empty(raw.get("task_version"), "task_version", "2.0")[:64],
            "task_instance_id": _non_empty(
                raw.get("task_instance_id"), "task_instance_id", "study1-default"
            )[:128],
            "consent_version": _non_empty(
                raw.get("consent_version"), "consent_version", "study1-consent-v1"
            )[:64],
            "instrument_catalog_version": _non_empty(
                raw.get("instrument_catalog_version"),
                "instrument_catalog_version",
                "study1-instruments-v2",
            )[:64],
            "instrument_catalog_checksum": _non_empty(
                raw.get("instrument_catalog_checksum"),
                "instrument_catalog_checksum",
                "study1-instruments-v2-dev",
            )[:128],
            "ui_schema_version": _non_empty(
                raw.get("ui_schema_version"), "ui_schema_version", "study1-ui-v2"
            )[:64],
            "phase_durations_seconds": durations,
            "minimum_review_seconds": minimum_review,
            "laboratory_timezone": _validate_timezone(raw.get("laboratory_timezone")),
            "recording_mode": recording_mode,
            "authority_level": authority,
            "proxy_provider": _non_empty(raw.get("proxy_provider"), "proxy_provider", "mock")[:64],
            "proxy_model": _non_empty(raw.get("proxy_model"), "proxy_model", "study1-proxy-v2")[:128],
            "proxy_prompt_version": _non_empty(
                raw.get("proxy_prompt_version"), "proxy_prompt_version", "study1-proxy-neutral-v2"
            )[:128],
            "proxy_prompt_checksum": _non_empty(
                raw.get("proxy_prompt_checksum"),
                "proxy_prompt_checksum",
                "study1-proxy-neutral-v2-dev",
            )[:128],
            "proxy_sampling": copy.deepcopy(raw.get("proxy_sampling") or {"temperature": 0, "top_p": 1}),
            "asr_provider": _non_empty(raw.get("asr_provider"), "asr_provider", "mock")[:64],
            "asr_model": _non_empty(raw.get("asr_model"), "asr_model", "study1-asr-v2")[:128],
            "tts_provider": _non_empty(raw.get("tts_provider"), "tts_provider", "mock")[:64],
            "tts_model": _non_empty(raw.get("tts_model"), "tts_model", "study1-tts-v2")[:128],
            "tts_voice": _non_empty(raw.get("tts_voice"), "tts_voice", "neutral-en-us")[:128],
            "summary_provider": _non_empty(raw.get("summary_provider"), "summary_provider", "mock")[:64],
            "summary_model": _non_empty(raw.get("summary_model"), "summary_model", "study1-summary-v2")[:128],
            "summary_prompt_version": _non_empty(
                raw.get("summary_prompt_version"), "summary_prompt_version", "study1-summary-neutral-v2"
            )[:128],
            "summary_prompt_checksum": _non_empty(
                raw.get("summary_prompt_checksum"),
                "summary_prompt_checksum",
                "study1-summary-neutral-v2-dev",
            )[:128],
            "summary_template_version": _non_empty(
                raw.get("summary_template_version"),
                "summary_template_version",
                "study1-five-section-v1",
            )[:64],
            "summary_sampling": copy.deepcopy(raw.get("summary_sampling") or {"temperature": 0, "top_p": 1}),
            "summary_retry_count": retry_count,
            "summary_failure_policy": summary_failure,
            "transcript_access_policy": _non_empty(
                raw.get("transcript_access_policy"),
                "transcript_access_policy",
                "principal_after_delegation",
            )[:64],
            "retention_policy": copy.deepcopy(
                raw.get("retention_policy")
                or {"review_days": 30, "deletion_days": 365, "media_disposition": "controlled_purge"}
            ),
            "media_access_policy": _non_empty(
                raw.get("media_access_policy"), "media_access_policy", "authorized_phase_only"
            )[:64],
            "feature_flags": {"resync_enabled": False, "video_enabled": False},
            "build_ids": clean_build_ids,
            "role_assignment_mode": _non_empty(
                raw.get("role_assignment_mode"), "role_assignment_mode", "fixed"
            )[:32],
            "randomization_seed": _non_empty(
                raw.get("randomization_seed"), "randomization_seed", secrets.token_hex(8)
            )[:64],
            "require_consent": bool(raw.get("require_consent", False)),
            "structured_instruments": True,
        }
    )
    return normalized


def canonical_protocol_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item),
    )


def compute_protocol_checksum(
    config: Mapping[str, Any],
    task: Any | None = None,
    assignments: Any | None = None,
    materials: Any | None = None,
) -> str:
    payload: dict[str, Any] = {"config": copy.deepcopy(dict(config))}
    if task is not None:
        payload["task"] = copy.deepcopy(task)
    if assignments is not None:
        payload["assignments"] = copy.deepcopy(assignments)
    if materials is not None:
        payload["materials"] = copy.deepcopy(materials)
    return hashlib.sha256(canonical_protocol_json(payload).encode("utf-8")).hexdigest()


def clone_protocol_values(config: Mapping[str, Any]) -> ProtocolConfigV2:
    cloned = copy.deepcopy(dict(config))
    cloned["randomization_seed"] = secrets.token_hex(8)
    return normalize_protocol_config_v2(cloned)


def freeze_protocol_snapshot(
    snapshot: Mapping[str, Any],
    *,
    task: Any | None = None,
    assignments: Any | None = None,
    materials: Any | None = None,
    actor: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return an immutable snapshot projection with its final checksum."""

    result = copy.deepcopy(dict(snapshot))
    config = normalize_protocol_config_v2(result.get("canonical_config") or {})
    timestamp = now or datetime.now(timezone.utc)
    result.update(
        {
            "canonical_config": config,
            "checksum": compute_protocol_checksum(config, task, assignments, materials),
            "frozen": True,
            "frozen_at": timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "frozen_by": (actor or {}).get("participant_id") or "researcher",
        }
    )
    return result


def assert_protocol_runtime_match(
    snapshot: Mapping[str, Any], runtime: Mapping[str, Any]
) -> None:
    """Reject runtime provider/build values that differ from the frozen record."""

    def mismatch(message: str) -> None:
        # The protocol module stays importable without importing the service
        # layer, while callers still receive the domain error used by routes.
        from .services import Study1ServiceError

        raise Study1ServiceError("PROTOCOL_RUNTIME_MISMATCH", message, 409)

    expected = dict(snapshot.get("canonical_config") or {})
    supplied_checksum = runtime.get("configuration_checksum")
    if supplied_checksum and supplied_checksum != snapshot.get("checksum"):
        mismatch("Runtime configuration checksum differs from the frozen Session")
    expected_builds = expected.get("build_ids") or {}
    actual_builds = runtime.get("build_ids") or {}
    for component, value in expected_builds.items():
        actual = actual_builds.get(component, runtime.get(f"{component}_build_id"))
        if actual is None:
            actual = runtime.get(component)
        if actual is not None and str(actual) != str(value):
            mismatch(f"Runtime {component} build does not match the frozen Session")
    for key in ("recording_mode", "authority_level", "proxy_model", "summary_model"):
        if key in runtime and runtime[key] != expected.get(key):
            mismatch(f"Runtime {key} differs from the frozen Session")
