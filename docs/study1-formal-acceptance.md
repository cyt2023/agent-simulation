# Study 1 Formal Acceptance

Study 1 acceptance has two levels.

Technical acceptance means the codebase passes automated checks and produces a
verifiable release manifest and reconstructable export. Data-collection-ready
means technical acceptance plus all external study, infrastructure, credential,
and pilot signoffs.

## Automated Checks

Run from the repository root:

```powershell
python scripts/build_study1_release_manifest.py --output release/study1-release-manifest.json
python scripts/verify_study1_release.py release/study1-release-manifest.json
python -m pytest -p no:cacheprovider backend/tests/study1 media_service/tests tests/acceptance -q
cd frontend
npm.cmd test -- --run
npm.cmd run build
```

These checks verify role permissions, phase control, media command contracts,
summary governance, review telemetry, export integrity, release checksum, and
export reconstruction.

## Required External Signoffs

The following are outside automated testing and must be recorded before formal
data collection:

- IRB or ethics approval for the exact consent text and study protocol.
- Production WSS/TURN and LiveKit configuration on real lab devices.
- Production ASR, LLM, TTS, database, storage, and service credentials.
- Real participant pilot review covering role isolation, audio quality, ASR
  timestamps, Summary neutrality, handoff, final measurements, markers, replay,
  and export completeness.

If any external signoff is missing, the release verifier reports
`technical_acceptance`.
