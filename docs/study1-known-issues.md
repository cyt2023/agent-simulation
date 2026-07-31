# Study 1 Known Issues

## Current Technical Acceptance Limits

- Local Docker and Mock provider runs do not prove production ASR, LLM, TTS,
  LiveKit WSS/TURN, or real microphone reliability.
- A release manifest with incomplete external signoffs is technical acceptance
  only, even if all automated tests pass.
- Export integrity warnings require researcher review before analysis.

## Issue Log Template

| Date | Release ID | Severity | Component | Description | Decision |
| --- | --- | --- | --- | --- | --- |
| YYYY-MM-DD | study1-... | low/medium/high | A/B/UI/ops | What happened | accept/retry/fix/terminate |

## Severity Guide

- High: role isolation, material authorization, handoff, release checksum, or
  consent failure.
- Medium: audio quality, ASR timing, Summary QA, export completeness, or
  telemetry loss that can affect analysis.
- Low: cosmetic UI, operator friction, or recoverable local setup issue.
