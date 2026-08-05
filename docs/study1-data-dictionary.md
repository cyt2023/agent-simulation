# Study 1 data dictionary

This document describes the canonical export files produced by Study 1.

## Core manifest files

- `export_manifest.json`: schema version, session id, build versions, and checksums for canonical export files.
- `integrity_report.json`: actionable errors and warnings. `MEDIA_EXPORT_UNAVAILABLE` means the A-side export exists but no B-side audio/media bundle was available.
- `media_manifest.json`: normalized recording metadata and room-clock identifiers.
- `meeting_minutes.md`: human-readable neutral summary and chronological transcript. Every utterance is explicitly labelled as a real human role (`P`, `T1`, or `T2`) or `AI Proxy (X)`.
- `meeting_minutes.csv`: analysis-ready version of the attributed transcript with `speaker_type`, `speaker_role`, `speaker_label`, timestamps, text, and segment id.

## Normalized research records

- `normalized/events.jsonl`: append-only server timeline.
- `normalized/utterances.jsonl`: transcript segments with `utterance_id`, speaker, text, timing, recording id, and clock id.
- `normalized/markers.jsonl`: typed participant/researcher markers and their segment/recording references.
- `normalized/replay_plans.json`: deterministic interview replay windows generated from markers.
- `normalized/decisions.jsonl`: individual and team decisions.
- `normalized/instrument_responses.jsonl`: ordered formal measurement responses.
- `normalized/review_events.jsonl`: Review reading, transcript, replay, visibility, and scroll telemetry.
- `normalized/incidents.jsonl`: coded incidents using the Study 1 incident catalog.
- `normalized/materials.jsonl`: Hidden Profile material assignment metadata.
- `normalized/artifacts.jsonl`: generated artifact manifest, including Summary and transcript artifacts.
- `normalized/summary_qa.jsonl`: private researcher Summary QA annotations.

Legacy CSV/JSON files remain in the bundle for compatibility, but new analyses should prefer the normalized files above.
