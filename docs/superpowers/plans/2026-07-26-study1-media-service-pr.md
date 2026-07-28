## Summary

- add an independent FastAPI/PostgreSQL Study 1 media service with LiveKit audio rooms, one server-side Proxy, timestamped ASR, neutral cited summaries, per-runtime recording, durable callbacks, recovery, replay, and complete media export
- integrate A as the sole workflow/identity/data authority, including explicit P material authorization, role-filtered media access, researcher operations, and merged final exports
- add the participant device/audio/review experience and researcher media status controls while keeping P isolated from the Proxy meeting and X absent from Sync

## Security and experiment invariants

- P receives no Proxy-room token; X receives no Sync-room token
- the hidden Sync recorder is subscribe-only and cannot publish media or data
- X receives only P-selected Hidden Profile material IDs validated by A
- B never advances A's experiment phase or writes A's primary database
- production media secrets have no Compose defaults and placeholder secrets fail at startup

## Test plan

- [x] `python -m pytest -p no:cacheprovider media_service\tests -q` (`49 passed`)
- [x] `$env:PYTHONPATH=(Resolve-Path 'backend').Path; python -m pytest -p no:cacheprovider backend\tests\study1 -q` (`43 passed`)
- [x] `npm --prefix frontend test -- --run` (`10 passed`)
- [x] `npm --prefix frontend run build`
- [x] `docker compose config --quiet` with required media secrets supplied
- [x] `git diff --check`
- [ ] Docker image build and real PostgreSQL/LiveKit smoke test: Docker Desktop Linux daemon was not running in the implementation environment
