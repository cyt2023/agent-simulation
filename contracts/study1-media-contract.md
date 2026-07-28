# Study 1 A/B Media Contract

Version: `1.1-v1-extension`

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
- `END_CURRENT_MEETING`
- `BEGIN_HANDOFF`
- `START_SYNC_MEETING`
- `REGENERATE_SUMMARY`
- `STOP_SESSION`

`END_CURRENT_MEETING` is the researcher-authorized explicit end for the active
Proxy or synchronous meeting. `REGENERATE_SUMMARY` requires `reason`,
`source_transcript_checksum`, and `source_summary_version`; its semantic
idempotency key is the source checksum/version pair. These are v1 extensions
pending name/envelope alignment with A; their security and idempotency semantics
must be preserved.

`command_id` is the idempotency key. Repeating a command returns the original
acceptance outcome and must not start or stop anything twice. `phase_version`
must be copied into related B events.

Example acceptance:

```json
{
  "accepted": true,
  "duplicate": false,
  "command_id": "uuid",
  "runtime_state": "PREPARING"
}
```

For `START_PROXY_MEETING`, A replaces any browser/researcher-provided context
with a server-built `authorized_context` containing the locked P Proxy
configuration and only P-authorized materials. B never queries A tables and
never receives unshared T1/T2 private materials.

P's locked `proxy_config` submission must contain
`authorization_confirmed: true` and an `authorized_material_ids` list. A
validates every selected ID against P's own Hidden Profile assignment. The
submission ID is used as both the configuration and authorization audit ID;
an absent confirmation, an unknown ID, or a T1/T2 material ID fails closed.
An empty list is valid only when P explicitly confirms that no material is
shared.

Accepted commands have durable `accepted`, `processing`, `completed`, and
`failed` states. On startup B replays persisted `accepted`/`processing`
envelopes through idempotent runtime operations before accepting new work.

## A-proxied media access and operations

Browsers call A only. A copies token identity and its authoritative phase into:

- `POST {B_SERVICE}/internal/media-access`
- `GET {B_SERVICE}/internal/sessions/{session_id}/status`
- `GET {B_SERVICE}/internal/sessions/{session_id}/export`
- `GET {B_SERVICE}/internal/sessions/{session_id}/recordings/{recording_id}`

All four require `Authorization: Bearer {A_TO_B_SERVICE_TOKEN}`. Proxy-room
access is T1/T2/X only; P receives 403 and is never issued a token. Sync-room
access is P/T1/T2 only; X is never issued a token. Tokens expire within five
minutes and allow microphone audio only. Recording reads require a bounded
Range and are proxied by A only after principal Review authorization.

B joins the Sync room as a hidden subscribe-only recorder identity. That
identity cannot publish audio or data and is never returned by the media-access
endpoint. It records and transcribes P/T1/T2 without starting Proxy LLM/TTS.

B's export is a ZIP scoped to one opaque `session_id`. A places its contents
under `media/` in the final Study 1 export. No B filesystem path is accepted
from a browser or copied into A's database.

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
  "content": "T1 stated: The north route is shorter. [segment:seg-1]",
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

Summary generation accepts only final transcript segments. Each generated
fact must cite existing `segment_id` values and pass neutral-language and
lexical grounding checks. B retries an invalid result once with the identical
transcript, prompt, model, and provider configuration; after the second
failure it publishes `MEDIA_ERROR` and does not mark the summary ready.

`HANDOFF_COMPLETE` is emitted only after X has stopped and P/T1/T2 all have a
successful server-recorded device preflight. Missing readiness produces an
auditable `MEDIA_ERROR` with `HANDOFF_MEDIA_NOT_READY` and leaves A in HANDOFF.

## MockMediaGateway

The repository implementation records and acknowledges valid command envelopes
in memory and creates no media. The researcher-only Mock completion endpoint
generates the same event envelope that B would send:

- PROXY_MEETING → `MEETING_ENDED`
- HANDOFF → `HANDOFF_COMPLETE`
- SYNC_MEETING → `MEETING_ENDED`

This supports workflow and data tests without claiming any live meeting, Proxy
runtime, voice, or recording capability.
