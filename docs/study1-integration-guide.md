# Study 1 Integration Guide

This guide describes the current Study 1 A/B integration boundary.

## Services

| Service | Local URL | Container URL | Notes |
| --- | --- | --- | --- |
| Frontend | `http://localhost:8080` | `http://frontend:80` | Single browser entry point |
| Backend A | `http://localhost:5000` | `http://backend:5000` | REST, Socket.IO, roles, phases, data |
| Media B | internal only | `http://media-service:8000` | Audio room, ASR, LLM, TTS, recording |
| LiveKit | `ws://localhost:7880` | `ws://livekit:7880` | Audio-only RTC |
| PostgreSQL | `127.0.0.1:5432` | `postgres:5432` | Separate A/B schemas |

## Required Environment

```dotenv
STUDY1_RESEARCHER_KEY=replace-with-researcher-key
STUDY1_TOKEN_SECRET=replace-with-token-secret
STUDY1_INTERNAL_API_KEY=replace-with-b-to-a-key
A_TO_B_SERVICE_TOKEN=replace-with-a-to-b-key
MEDIA_GATEWAY_MODE=http
MEDIA_SERVICE_URL=http://media-service:8000
LIVEKIT_PUBLIC_URL=ws://localhost:7880
STUDY1_RELEASE_ID=<release manifest release_id>
STUDY1_RELEASE_CHECKSUM=<release manifest checksum>
```

Do not commit real credentials.

## A to B Commands

Browser clients never call B directly. Researchers call A:

```http
POST /api/study1/sessions/{session_id}/media-commands
Authorization: Bearer {researcher_token}
Content-Type: application/json
```

```json
{
  "command": "START_PROXY_MEETING",
  "command_id": "optional-idempotency-key",
  "payload": {}
}
```

A constructs the authoritative B envelope. If `STUDY1_RELEASE_ID` and
`STUDY1_RELEASE_CHECKSUM` are set, A includes:

```json
{
  "payload": {
    "release": {
      "release_id": "study1-...",
      "checksum": "sha256..."
    }
  }
}
```

B rejects the command with `409` if its configured release identity differs.

For `START_PROXY_MEETING`, A ignores browser context and sends only locked
P-authorized material plus the locked Proxy configuration. X never receives
T1/T2 private material.

## B to A Events and Artifacts

B calls A with `X-Study1-Internal-Key`.

```http
POST /api/internal/study1/media-events
POST /api/internal/study1/sessions/{session_id}/artifacts
```

Events are idempotent by `event_id` and must include the current
`phase_version`. Stale phase events are rejected and do not advance the
experiment automatically.

## Export and Acceptance

Researcher export returns a ZIP containing the platform records and B media
bundle. The acceptance verifier reconstructs relationships among recordings,
utterances, markers, decisions, summaries, and integrity reports.

```powershell
python -m pytest -p no:cacheprovider tests/acceptance -q
```
