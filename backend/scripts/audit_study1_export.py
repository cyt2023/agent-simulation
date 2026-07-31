"""Audit a Study 1 export ZIP and print its integrity report.

Usage:
    python backend/scripts/audit_study1_export.py path/to/export.zip
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path


REQUIRED_FILES = {
    "export_manifest.json",
    "integrity_report.json",
    "media_manifest.json",
    "normalized/events.jsonl",
    "normalized/utterances.jsonl",
    "normalized/markers.jsonl",
    "normalized/replay_plans.json",
    "normalized/decisions.jsonl",
    "normalized/review_events.jsonl",
}


def audit(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        missing = sorted(REQUIRED_FILES - names)
        report = json.loads(archive.read("integrity_report.json"))
        manifest = json.loads(archive.read("export_manifest.json"))
    status = "failed" if missing or report.get("errors") else "passed"
    return {
        "status": status,
        "schema_version": manifest.get("schema_version"),
        "session_id": manifest.get("session_id"),
        "missing_files": missing,
        "integrity_errors": report.get("errors", []),
        "integrity_warnings": report.get("warnings", []),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python backend/scripts/audit_study1_export.py path/to/export.zip")
        return 2
    result = audit(Path(argv[1]))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
