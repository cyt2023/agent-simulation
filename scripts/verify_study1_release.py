from __future__ import annotations

import argparse
import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts.build_study1_release_manifest import (
        REQUIRED_EXTERNAL_SIGNOFFS,
        UNKNOWN_VALUES,
        release_checksum,
    )
except ModuleNotFoundError:
    from build_study1_release_manifest import (  # type: ignore[no-redef]
        REQUIRED_EXTERNAL_SIGNOFFS,
        UNKNOWN_VALUES,
        release_checksum,
    )


@dataclass(frozen=True)
class ReleaseVerificationResult:
    status: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExportReconstructionResult:
    status: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    utterance_count: int = 0
    recording_count: int = 0
    marker_count: int = 0


def verify_release_manifest(manifest: Mapping[str, Any]) -> ReleaseVerificationResult:
    errors: list[str] = []
    warnings: list[str] = []
    expected_checksum = release_checksum(manifest)
    if manifest.get("checksum") != expected_checksum:
        errors.append("RELEASE_CHECKSUM_MISMATCH")
    build_versions = manifest.get("build_versions") or {}
    for component, value in build_versions.items():
        if str(value).strip().casefold() in UNKNOWN_VALUES:
            errors.append(f"UNKNOWN_{str(component).upper()}_BUILD")
    signoffs = (manifest.get("acceptance") or {}).get("external_signoffs") or {}
    missing = [name for name in REQUIRED_EXTERNAL_SIGNOFFS if not signoffs.get(name)]
    if missing:
        warnings.append("EXTERNAL_SIGNOFFS_INCOMPLETE")
    if errors:
        status = "failed"
    elif missing:
        status = "technical_acceptance"
    else:
        status = "data_collection_ready"
    return ReleaseVerificationResult(status=status, errors=errors, warnings=warnings)


def reconstruct_study1_export(bundle: str | Path | bytes | io.BytesIO) -> ExportReconstructionResult:
    errors: list[str] = []
    warnings: list[str] = []
    with _open_zip(bundle) as archive:
        names = set(archive.namelist())
        required = {
            "export_manifest.json",
            "media_manifest.json",
            "normalized/utterances.jsonl",
            "normalized/markers.jsonl",
            "integrity_report.json",
        }
        missing = sorted(required - names)
        if missing:
            return ExportReconstructionResult(
                status="failed",
                errors=[f"MISSING:{name}" for name in missing],
            )
        manifest = _read_json(archive, "export_manifest.json")
        media_manifest = _read_json(archive, "media_manifest.json")
        integrity = _read_json(archive, "integrity_report.json")
        utterances = _read_jsonl(archive, "normalized/utterances.jsonl")
        markers = _read_jsonl(archive, "normalized/markers.jsonl")
    if manifest.get("schema_version") != "study1-export-v2":
        errors.append("UNSUPPORTED_EXPORT_SCHEMA")
    integrity_errors = integrity.get("errors") or []
    if integrity_errors:
        warnings.extend(str(error) for error in integrity_errors)
    recordings = {
        str(item.get("recording_id")): item
        for item in media_manifest.get("recordings") or []
        if item.get("recording_id")
    }
    utterance_ids = {str(item.get("utterance_id")) for item in utterances}
    for utterance in utterances:
        recording_id = utterance.get("recording_id")
        if recording_id and str(recording_id) not in recordings:
            errors.append("UTTERANCE_RECORDING_NOT_FOUND")
            continue
        if recording_id:
            expected_clock = recordings[str(recording_id)].get("clock_id")
            if expected_clock and utterance.get("clock_id") != expected_clock:
                errors.append("UTTERANCE_CLOCK_MISMATCH")
    for marker in markers:
        for segment_id in marker.get("segment_ids") or []:
            if str(segment_id) not in utterance_ids:
                errors.append("MARKER_SEGMENT_NOT_FOUND")
        for recording_id in marker.get("recording_ids") or []:
            if str(recording_id) not in recordings:
                errors.append("MARKER_RECORDING_NOT_FOUND")
    return ExportReconstructionResult(
        status="failed" if errors else "reconstructable",
        errors=sorted(set(errors)),
        warnings=sorted(set(warnings)),
        utterance_count=len(utterances),
        recording_count=len(recordings),
        marker_count=len(markers),
    )


def _open_zip(bundle: str | Path | bytes | io.BytesIO):
    if isinstance(bundle, (str, Path)):
        return zipfile.ZipFile(bundle)
    if isinstance(bundle, bytes):
        return zipfile.ZipFile(io.BytesIO(bundle))
    bundle.seek(0)
    return zipfile.ZipFile(bundle)


def _read_json(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    return json.loads(archive.read(name).decode("utf-8"))


def _read_jsonl(archive: zipfile.ZipFile, name: str) -> list[dict[str, Any]]:
    content = archive.read(name).decode("utf-8").strip()
    if not content:
        return []
    return [json.loads(line) for line in content.splitlines()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a Study 1 release or export.")
    parser.add_argument("path")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    if args.export:
        result = reconstruct_study1_export(args.path)
    else:
        result = verify_release_manifest(json.loads(Path(args.path).read_text(encoding="utf-8")))
    print(json.dumps(result.__dict__, indent=2, sort_keys=True))
    return 0 if not result.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
