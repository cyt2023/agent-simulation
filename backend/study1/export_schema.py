"""Canonical Study 1 export schema helpers."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any


CANONICAL_EXPORT_SCHEMA_VERSION = "study1-export-v2"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_export_manifest(
    *,
    session: dict[str, Any],
    file_checksums: dict[str, str],
    formal_certifiable: bool,
) -> dict[str, Any]:
    return {
        "schema_version": CANONICAL_EXPORT_SCHEMA_VERSION,
        "session_id": session["session_id"],
        "protocol_version": session.get("protocol_version"),
        "task_version": session.get("task_version"),
        "formal_certifiable": formal_certifiable,
        "build_versions": {
            "backend": os.environ.get("STUDY1_BACKEND_BUILD_VERSION", "development"),
            "frontend": os.environ.get("STUDY1_FRONTEND_BUILD_VERSION", "development"),
            "media_service": os.environ.get(
                "STUDY1_MEDIA_SERVICE_BUILD_VERSION", "development"
            ),
        },
        "checksums": file_checksums,
    }


def checksum_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
