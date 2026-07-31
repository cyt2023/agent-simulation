from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "study1-release-v1"
REQUIRED_EXTERNAL_SIGNOFFS = (
    "irb_approval",
    "production_wss_turn",
    "production_credentials",
    "real_participant_pilots",
)
UNKNOWN_VALUES = {"", "unknown", "unset", "latest"}


class ReleaseError(ValueError):
    pass


def build_release_manifest(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    values = dict(overrides or {})
    build_versions = _build_versions(values)
    _reject_unknown_builds(build_versions)
    external_signoffs = _external_signoffs(values.get("external_signoffs"))
    requested_status = str(values.get("requested_status") or "technical_acceptance")
    missing_signoffs = [
        name for name in REQUIRED_EXTERNAL_SIGNOFFS if not external_signoffs.get(name)
    ]
    acceptance_status = (
        "data_collection_ready"
        if requested_status == "data_collection_ready" and not missing_signoffs
        else "technical_acceptance"
    )
    source = values.get("source") or {}
    protocol = _protocol(values.get("protocol") or {})
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "release_id": str(values.get("release_id") or _release_id(build_versions)),
        "created_at": _utc_now(),
        "source": {
            "commit": str(source.get("commit") or values.get("commit") or _git_value("rev-parse", "HEAD")),
            "branch": str(source.get("branch") or values.get("branch") or _git_value("branch", "--show-current")),
            "dirty_worktree": bool(source.get("dirty_worktree", _git_dirty())),
        },
        "build_versions": build_versions,
        "docker_images": _docker_images(values.get("docker_images") or {}),
        "database_revisions": _database_revisions(values.get("database_revisions") or {}),
        "protocol": protocol,
        "providers": _providers(values.get("providers") or {}),
        "prompts": _prompts(values.get("prompts") or {}),
        "sampling": _sampling(values.get("sampling") or {}),
        "version_catalog": _version_catalog(values.get("version_catalog") or {}),
        "acceptance": {
            "requested_status": requested_status,
            "status": acceptance_status,
            "external_signoffs": external_signoffs,
            "missing_external_signoffs": missing_signoffs,
            "automated_gates": _automated_gates(),
            "technical_acceptance_only": bool(missing_signoffs),
        },
    }
    checksum = release_checksum(manifest)
    return {**manifest, "checksum": checksum}


def release_checksum(manifest: Mapping[str, Any]) -> str:
    clean = copy.deepcopy(dict(manifest))
    clean.pop("checksum", None)
    return hashlib.sha256(_canonical_json(clean).encode("utf-8")).hexdigest()


def write_release_manifest(
    overrides: Mapping[str, Any] | None = None,
    output_path: str | Path = "release/study1-release-manifest.json",
) -> dict[str, Any]:
    manifest = build_release_manifest(overrides)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _build_versions(values: Mapping[str, Any]) -> dict[str, str]:
    explicit = dict(values.get("build_versions") or {})
    return {
        "backend": str(
            explicit.get("backend")
            or values.get("backend_build")
            or os.environ.get("STUDY1_BACKEND_BUILD_VERSION")
            or "backend-local"
        ),
        "frontend": str(
            explicit.get("frontend")
            or values.get("frontend_build")
            or os.environ.get("STUDY1_FRONTEND_BUILD_VERSION")
            or "frontend-local"
        ),
        "media_service": str(
            explicit.get("media_service")
            or values.get("media_build")
            or os.environ.get("STUDY1_MEDIA_SERVICE_BUILD_VERSION")
            or "media-local"
        ),
    }


def _reject_unknown_builds(build_versions: Mapping[str, str]) -> None:
    for component, value in build_versions.items():
        if str(value).strip().casefold() in UNKNOWN_VALUES:
            raise ReleaseError(f"{component} build cannot be unknown")


def _external_signoffs(value: Any) -> dict[str, bool]:
    source = value if isinstance(value, Mapping) else {}
    return {name: bool(source.get(name, False)) for name in REQUIRED_EXTERNAL_SIGNOFFS}


def _protocol(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "protocol_version": str(value.get("protocol_version") or "study1-audio-formal-v2"),
        "media_contract_version": str(value.get("media_contract_version") or "study1-media-contract-v2"),
        "phase_schema_version": str(value.get("phase_schema_version") or "study1-phase-v2"),
        "task_version": str(value.get("task_version") or "2.0"),
        "task_instance_id": str(value.get("task_instance_id") or "study1-default"),
        "task_checksum": str(value.get("task_checksum") or _hash_text("study1-default-task")),
        "facts_checksum": str(value.get("facts_checksum") or _hash_text("study1-default-facts")),
    }


def _providers(value: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    defaults = {
        "asr": {"provider": "mock", "model": "study1-asr-v2"},
        "llm": {"provider": "mock", "model": "study1-proxy-v2"},
        "tts": {"provider": "mock", "model": "study1-tts-v2"},
        "summary": {"provider": "mock", "model": "study1-summary-v2"},
    }
    return {
        name: {
            "provider": str(dict(value.get(name) or {}).get("provider") or default["provider"]),
            "model": str(dict(value.get(name) or {}).get("model") or default["model"]),
        }
        for name, default in defaults.items()
    }


def _prompts(value: Mapping[str, Any]) -> dict[str, str]:
    return {
        "proxy_prompt_version": str(value.get("proxy_prompt_version") or "study1-proxy-neutral-v2"),
        "proxy_prompt_checksum": str(value.get("proxy_prompt_checksum") or _hash_text("study1-proxy-neutral-v2")),
        "summary_prompt_version": str(value.get("summary_prompt_version") or "study1-summary-neutral-v2"),
        "summary_prompt_checksum": str(value.get("summary_prompt_checksum") or _hash_text("study1-summary-neutral-v2")),
        "summary_template_version": str(value.get("summary_template_version") or "study1-five-section-v1"),
        "summary_template_checksum": str(value.get("summary_template_checksum") or _hash_text("study1-five-section-v1")),
    }


def _sampling(value: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    proxy = dict(value.get("proxy") or {"temperature": 0, "top_p": 1})
    summary = dict(value.get("summary") or {"temperature": 0, "top_p": 1})
    return {"proxy": proxy, "summary": summary}


def _version_catalog(value: Mapping[str, Any]) -> dict[str, str]:
    defaults = {
        "consent": "study1-consent-v1",
        "instruments": "study1-instruments-v2",
        "marker_catalog": "study1-markers-v1",
        "replay_policy": "study1-replay-fixed-window-v1",
        "retention_policy": "study1-retention-v1",
        "study2_contract": "study2-readonly-contract-v1",
    }
    return {key: str(value.get(key) or default) for key, default in defaults.items()}


def _docker_images(value: Mapping[str, Any]) -> dict[str, str]:
    defaults = {
        "backend": "study1-backend:local",
        "frontend": "study1-frontend:local",
        "media_service": "study1-media-service:local",
        "postgres": "postgres:16-alpine",
        "livekit": "livekit/livekit-server:v1.9.6",
    }
    return {key: str(value.get(key) or default) for key, default in defaults.items()}


def _database_revisions(value: Mapping[str, Any]) -> dict[str, str]:
    return {
        "backend_schema": str(value.get("backend_schema") or "study1-schema-current"),
        "media_schema": str(value.get("media_schema") or "study1-media-schema-current"),
    }


def _automated_gates() -> list[dict[str, str]]:
    return [
        {
            "name": "release manifest build",
            "command": "python scripts/build_study1_release_manifest.py --output release/study1-release-manifest.json",
        },
        {
            "name": "release manifest verification",
            "command": "python scripts/verify_study1_release.py release/study1-release-manifest.json",
        },
        {"name": "backend study1 tests", "command": "python -m pytest -p no:cacheprovider backend/tests/study1 -q"},
        {"name": "media tests", "command": "python -m pytest -p no:cacheprovider media_service/tests -q"},
        {"name": "acceptance reconstruction", "command": "python -m pytest -p no:cacheprovider tests/acceptance -q"},
        {"name": "frontend tests", "command": "npm.cmd test -- --run"},
        {"name": "frontend build", "command": "npm.cmd run build"},
        {"name": "frontend audio e2e", "command": "npm.cmd run test:e2e"},
    ]


def _release_id(build_versions: Mapping[str, str]) -> str:
    seed = _canonical_json(build_versions)
    return f"study1-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_value(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or "local"
    except Exception:
        return "local"


def _git_dirty() -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        tracked_changes = [
            line
            for line in result.stdout.splitlines()
            if line.strip() and not line.startswith("?? ")
        ]
        return bool(tracked_changes)
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Study 1 release manifest.")
    parser.add_argument("--output", default="release/study1-release-manifest.json")
    parser.add_argument("--release-id")
    parser.add_argument("--backend-build")
    parser.add_argument("--frontend-build")
    parser.add_argument("--media-build")
    args = parser.parse_args()
    manifest = write_release_manifest(
        {
            key: value
            for key, value in {
                "release_id": args.release_id,
                "backend_build": args.backend_build,
                "frontend_build": args.frontend_build,
                "media_build": args.media_build,
            }.items()
            if value is not None
        },
        args.output,
    )
    print(json.dumps({"release_id": manifest["release_id"], "checksum": manifest["checksum"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
