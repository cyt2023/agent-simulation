# Study 1 — A: workflow, authorization, and data

This package implements the server-authoritative Study 1 workflow. It does not
implement LiveKit, RTC/WebRTC, microphones, ASR, TTS, a Proxy runtime, audio
recording, or a real meeting service. `MockMediaGateway` only validates and
records the fixed A/B command envelope.

## Configuration

Required in production:

```text
DATABASE_URL=postgresql://...
FLASK_SECRET_KEY=...
STUDY1_RESEARCHER_KEY=...
STUDY1_INTERNAL_API_KEY=...
```

Optional:

```text
STUDY1_TOKEN_SECRET=...
STUDY1_AUTH_TOKEN_TTL_SECONDS=43200
STUDY1_FRONTEND_BUILD_VERSION=...
STUDY1_BACKEND_BUILD_VERSION=...
```

Initialize tables with the existing command:

```bash
cd backend
python -m scripts.init_db
```

## Routes

Participant pages:

- `/study1/join/:token`
- `/study1/participant`

Researcher page:

- `/researcher/study1`

The researcher signs in with `STUDY1_RESEARCHER_KEY`, creates a session, and
receives three raw one-time invitation URLs. Only invitation hashes are stored.

Study 1 uses a dedicated bearer token, role-filtered DTOs, a single state
machine transition endpoint, and append-only event/submission/artifact/incident
records. It does not trust role or participant identifiers supplied in request
bodies or query strings.

## Tests

From the repository root:

```bash
set PYTHONPATH=backend
python -m pytest -p no:cacheprovider backend/tests/study1 -q
```

The suite includes a complete Mock flow from session creation through ZIP
export. A PostgreSQL deployment should additionally run `python -m
scripts.init_db` as a migration smoke test.

## Media boundary

See `contracts/study1-media-contract.md`. The frontend never calls B. B can only
submit events and artifacts through the internal-key-protected A endpoints.
