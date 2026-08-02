# Study 1 Pilot Checklist

Use this checklist before calling a release data-collection-ready.

## Supporting Artifacts

- Synthetic-audio pilot runner: `python scripts/run_study1_synthetic_audio_pilot.py --template stress --output-dir output/pilots/stress-01`
- Failure scenarios: `docs/study1-pilot-failure-scenarios.md`
- Stress template: `docs/study1-pilot-stress-template.md`
- Stability template: `docs/study1-pilot-stability-template.md`
- Usability template: `docs/study1-pilot-usability-template.md`
- Full protocol template: `docs/study1-pilot-full-template.md`

## Automated Gates

- Backend Study 1 tests pass.
- Media Service tests pass.
- Frontend tests and build pass.
- Acceptance export reconstruction passes.
- Release manifest verifies with no checksum error.

## Device and Network Pilots

- Three-device, 60-minute stability run completed.
- Ten stress runs completed, including reconnect, microphone denial, barge-in,
  handoff, Summary retry, transcript correction, and export.
- Browser support checked on the target lab machines.
- LiveKit WSS and TURN path verified outside localhost.

## Human Pilots

- Three to five usability pilots completed.
- Three to five full protocol pilots completed.
- Pilot reviewer checked role isolation, audio clarity, ASR timing, neutral
  Summary, final measures, markers, replay, and export integrity.

## Final Signoff

- IRB or ethics version recorded.
- Production credentials installed.
- Release manifest checksum stored with the pilot record.
- Known issues reviewed by the study owner.
