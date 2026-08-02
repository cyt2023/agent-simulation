from __future__ import annotations

import argparse
import hashlib
import json
import math
import wave
from array import array
from pathlib import Path
from typing import Any

SAMPLE_RATE_HZ = 8000
DEFAULT_DURATION_SECONDS = 12.0

SCENARIO_CATALOG: list[dict[str, str]] = [
    {
        "scenario": "reconnect",
        "failure_injection": "drop_link",
        "expected_observation": "The session reconnects without creating a second participant identity.",
    },
    {
        "scenario": "microphone_denial",
        "failure_injection": "deny_mic_permission",
        "expected_observation": "The participant sees a neutral technical prompt and can continue the pilot path.",
    },
    {
        "scenario": "barge_in",
        "failure_injection": "interrupt_tts",
        "expected_observation": "An active human utterance cancels the current proxy playback once.",
    },
    {
        "scenario": "handoff",
        "failure_injection": "principal_return",
        "expected_observation": "Proxy speaking rights stop when the principal returns.",
    },
    {
        "scenario": "summary_retry",
        "failure_injection": "frozen_summary_retry",
        "expected_observation": "Summary retry uses the frozen configuration and records the reason.",
    },
    {
        "scenario": "transcript_correction",
        "failure_injection": "asr_correction",
        "expected_observation": "The correction is appended without overwriting the original transcript.",
    },
    {
        "scenario": "export",
        "failure_injection": "bundle_export",
        "expected_observation": "The final export contains media, transcript, summary, and integrity records.",
    },
]

TEMPLATE_RUNS: dict[str, list[str]] = {
    "stress": [
        "reconnect",
        "microphone_denial",
        "barge_in",
        "handoff",
        "summary_retry",
        "transcript_correction",
        "reconnect",
        "barge_in",
        "handoff",
        "export",
    ],
    "stability": ["reconnect"],
    "usability": ["summary_retry", "handoff", "export"],
    "full": ["reconnect", "barge_in", "handoff", "summary_retry", "export"],
}


def list_failure_scenarios() -> list[dict[str, str]]:
    return [dict(item) for item in SCENARIO_CATALOG]


def build_pilot_bundle(
    template: str,
    output_dir: str | Path,
    *,
    duration_seconds: float = DEFAULT_DURATION_SECONDS,
    sample_rate_hz: int = SAMPLE_RATE_HZ,
) -> dict[str, Any]:
    template_key = _normalize_template(template)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    runs = _build_runs(template_key)
    wave_path = output_path / "synthetic_audio.wav"
    bundle_path = output_path / "pilot_run.json"
    _write_synthetic_audio(wave_path, duration_seconds=duration_seconds, sample_rate_hz=sample_rate_hz, run_count=len(runs))
    wave_sha256 = hashlib.sha256(wave_path.read_bytes()).hexdigest()

    bundle = {
        "template": template_key,
        "pilot_id": f"study1-{template_key}-pilot",
        "run_count": len(runs),
        "scenario_catalog": list_failure_scenarios(),
        "runs": runs,
        "audio": {
            "wave_path": str(wave_path.resolve()),
            "wave_sha256": wave_sha256,
            "sample_rate_hz": sample_rate_hz,
            "duration_seconds": duration_seconds,
        },
        "bundle_path": str(bundle_path.resolve()),
    }
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return bundle


def _normalize_template(template: str) -> str:
    value = template.strip().casefold()
    if value not in TEMPLATE_RUNS:
        raise ValueError(f"Unknown pilot template: {template}")
    return value


def _build_runs(template: str) -> list[dict[str, str | int]]:
    scenario_lookup = {item["scenario"]: item for item in SCENARIO_CATALOG}
    run_names = TEMPLATE_RUNS[template]
    return [
        {
            "run_index": index + 1,
            "scenario": scenario_name,
            "failure_injection": scenario_lookup[scenario_name]["failure_injection"],
            "expected_observation": scenario_lookup[scenario_name]["expected_observation"],
        }
        for index, scenario_name in enumerate(run_names)
    ]


def _write_synthetic_audio(
    path: Path,
    *,
    duration_seconds: float,
    sample_rate_hz: int,
    run_count: int,
) -> None:
    total_samples = int(duration_seconds * sample_rate_hz)
    samples = array("h")
    segment_duration = duration_seconds / max(run_count, 1)
    tone_duration = segment_duration * 0.25
    amplitude = 12000

    for sample_index in range(total_samples):
        timestamp = sample_index / sample_rate_hz
        segment_index = min(int(timestamp / segment_duration), max(run_count - 1, 0))
        phase = timestamp - (segment_index * segment_duration)
        if phase < tone_duration:
            frequency = 220.0 + (segment_index * 17.0)
            sample = int(amplitude * math.sin(2.0 * math.pi * frequency * timestamp))
        else:
            sample = 0
        samples.append(sample)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hz)
        wav_file.writeframes(samples.tobytes())


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic Study 1 synthetic-audio pilot bundle.")
    parser.add_argument("--template", choices=sorted(TEMPLATE_RUNS), default="stress")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration-seconds", type=float, default=DEFAULT_DURATION_SECONDS)
    parser.add_argument("--sample-rate-hz", type=int, default=SAMPLE_RATE_HZ)
    parser.add_argument("--list-scenarios", action="store_true")
    args = parser.parse_args()

    if args.list_scenarios:
        print(json.dumps(list_failure_scenarios(), indent=2, sort_keys=True))
        return 0

    bundle = build_pilot_bundle(
        args.template,
        args.output_dir,
        duration_seconds=args.duration_seconds,
        sample_rate_hz=args.sample_rate_hz,
    )
    print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
