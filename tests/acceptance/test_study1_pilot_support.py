from __future__ import annotations

import json
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


def test_study1_pilot_support_artifacts_exist():
    repo_root = Path(__file__).resolve().parents[2]
    required = [
        repo_root / "scripts" / "run_study1_synthetic_audio_pilot.py",
        repo_root / "docs" / "study1-pilot-failure-scenarios.md",
        repo_root / "docs" / "study1-pilot-stress-template.md",
        repo_root / "docs" / "study1-pilot-stability-template.md",
        repo_root / "docs" / "study1-pilot-usability-template.md",
        repo_root / "docs" / "study1-pilot-full-template.md",
    ]

    missing = [str(path) for path in required if not path.exists()]

    assert missing == []


def test_synthetic_audio_pilot_runner_builds_deterministic_bundle():
    from scripts.run_study1_synthetic_audio_pilot import build_pilot_bundle

    with TemporaryDirectory() as tmpdir:
        first = build_pilot_bundle("stress", Path(tmpdir) / "run-a")
        second = build_pilot_bundle("stress", Path(tmpdir) / "run-b")

        assert first["template"] == "stress"
        assert first["run_count"] == 10
        assert first["runs"][0]["scenario"] == "reconnect"
        assert first["runs"][-1]["scenario"] == "export"
        assert first["template"] == second["template"]
        assert first["run_count"] == second["run_count"]
        assert first["runs"] == second["runs"]
        assert first["scenario_catalog"] == second["scenario_catalog"]
        assert first["audio"]["sample_rate_hz"] == second["audio"]["sample_rate_hz"]
        assert first["audio"]["duration_seconds"] == second["audio"]["duration_seconds"]
        assert first["audio"]["wave_sha256"] == second["audio"]["wave_sha256"]

        bundle_path = Path(first["bundle_path"])
        with bundle_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        assert payload["template"] == "stress"
        assert payload["audio"]["sample_rate_hz"] == 8000
        assert payload["audio"]["duration_seconds"] == pytest.approx(12.0)
        assert Path(payload["audio"]["wave_path"]).exists()

        with wave.open(str(Path(payload["audio"]["wave_path"])), "rb") as wav:
            assert wav.getnchannels() == 1
            assert wav.getframerate() == 8000
