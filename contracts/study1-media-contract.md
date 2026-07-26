# Study 1 A/B Media Contract

Version: `1.0`

This is the complete integration boundary between the Study 1 workflow/data
service (A) and a future meeting/media service (B). A does not call ASR, LLM,
TTS, RTC, microphone, recording, or live-meeting APIs. The frontend never calls
B.

## Authentication and transport

- JSON over HTTPS.
- A authenticates to B using deployment-managed service credentials.
- B authenticates to A with `X-Study1-Internal-Key`.
- Timestamps are ISO-8601 UTC.
- UUID identifiers are treated as opaque strings.
- Both sides retain idempotency records across process restarts.

## A → B: the only command entry point

`POST {B_SERVICE}/internal/commands`

```json
{
  "command_id": "uuid",
  "session_id": "uuid",
  "phase_version": 3,
  "command": "START_PROXY_MEETING",
  "issued_at": "2026-01-02T03:04:05Z",
  "payload": {}
}
```

Allowed `command` values:

- `START_PROXY_MEETING`
- `BEGIN_HANDOFF`
- `START_SYNC_MEETING`
- `STOP_SESSION`

`command_id` is the idempotency key. Repeating a command returns the original
acceptance outcome and must not start or stop anything twice. `phase_version`
must be copied into related B events.

Example acceptance:

```json
{
  "accepted": true,
  "duplicate": false,
  "command_id": "uuid"
}
```

## B → A: the only media event entry point

`POST /api/internal/study1/media-events`

```json
{
  "event_id": "uuid",
  "session_id": "uuid",
  "phase_version": 3,
  "event_type": "MEDIA_READY",
  "occurred_at": "2026-01-02T03:04:06Z",
  "payload": {}
}
```

Allowed `event_type` values:

- `MEDIA_READY`
- `PARTICIPANT_JOINED`
- `PARTICIPANT_LEFT`
- `HANDOFF_COMPLETE`
- `MEDIA_ERROR`
- `MEETING_ENDED`

`event_id` is the idempotency key. A returns HTTP 200 with
`"duplicate": true` for an already processed event. A rejects stale
`phase_version` values with HTTP 409 and never advances a phase automatically.

Event effects in A:

- `MEDIA_READY`: media status becomes ready.
- `MEDIA_ERROR`: media status becomes error.
- `HANDOFF_COMPLETE`: satisfies the HANDOFF prerequisite.
- `MEETING_ENDED`: satisfies the current proxy/synchronous meeting prerequisite.
- participant join/leave events are audit records; they do not expose meeting
  content to the principal waiting room.

## B → A: artifact entry point

`POST /api/internal/study1/sessions/{session_id}/artifacts`

```json
{
  "artifact_id": "uuid",
  "type": "summary",
  "version": "1",
  "content": "Neutral summary text",
  "storage_uri": null,
  "checksum": "sha256 hex",
  "created_at": "2026-01-02T03:05:00Z",
  "generator_version": "mock-1",
  "metadata": {}
}
```

Allowed artifact types:

- `transcript`
- `summary`
- `recording_manifest`
- `agent_log_manifest`

Exactly one of inline `content` or `storage_uri` is normally supplied. Inline
content checksums are verified by A. `artifact_id` is idempotent; `(session_id,
type, version)` is unique. Summary readiness only satisfies a prerequisite.
Researcher action is still required to enter Review.

## MockMediaGateway

The repository implementation records and acknowledges valid command envelopes
in memory and creates no media. The researcher-only Mock completion endpoint
generates the same event envelope that B would send:

- PROXY_MEETING → `MEETING_ENDED`
- HANDOFF → `HANDOFF_COMPLETE`
- SYNC_MEETING → `MEETING_ENDED`

This supports workflow and data tests without claiming any live meeting, Proxy
runtime, voice, or recording capability.
