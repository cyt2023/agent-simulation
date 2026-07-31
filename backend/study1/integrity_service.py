"""Actionable integrity reports for Study 1 exports."""

from __future__ import annotations

from typing import Any


def build_integrity_report(
    *,
    missing_submissions: list[str],
    missing_artifacts: list[str],
    missing_current_phase_prerequisites: list[str],
    incidents: list[dict[str, Any]],
    override_events: list[dict[str, Any]],
    media_manifest: dict[str, Any],
    configuration_checksum: str | None,
    generated_at: str,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if missing_submissions:
        errors.append("SUBMISSIONS_INCOMPLETE")
    if missing_artifacts:
        errors.append("ARTIFACTS_INCOMPLETE")
    if missing_current_phase_prerequisites:
        errors.append("PHASE_PREREQUISITES_INCOMPLETE")
    if not media_manifest.get("recordings"):
        errors.append("MEDIA_EXPORT_UNAVAILABLE")
    if override_events:
        warnings.append("MANUAL_OVERRIDES_PRESENT")
    if incidents:
        warnings.append("INCIDENTS_PRESENT")

    return {
        "complete": not errors,
        "certification_status": "certifiable" if not errors else "technical_acceptance",
        "errors": errors,
        "warnings": warnings,
        "missing_submissions": missing_submissions,
        "missing_artifacts": missing_artifacts,
        "missing_current_phase_prerequisites": missing_current_phase_prerequisites,
        "incident_count": len(incidents),
        "override_count": len(override_events),
        "configuration_checksum": configuration_checksum,
        "generated_at": generated_at,
    }
