# Study 2 Read-only Contract v1

## Scope

Study 1 exposes the versioned `GET /api/study2/v1/sessions/{session_id}`
boundary for Study 2 consumers. It is a projection boundary, not a Study 1
control API: no endpoint accepts writes or returns an unfiltered session,
identity mapping, material, media, or arbitrary telemetry payload.

All endpoints require the existing Study 1 bearer token and return
`contract_version: "study2-readonly-contract-v1"`.

## Resources

| Path suffix | Read model |
| --- | --- |
| `/utterances` | Transcript utterances visible in the current Study 1 context. |
| `/decisions` | The caller's individual decisions, plus any team decision. |
| `/facts` | Atomic task facts visible to the caller's Study 1 role. |
| `/proxy-authority` | Frozen Proxy authority level and authorized material IDs. |
| `/baseline-recap` | The caller's pre-delegation decision recap. |
| `/features` | Read-only feature state; `resync_enabled` is always `false`. |
| `/module-telemetry` | Only allowlisted, field-filtered module telemetry. |

`utterances`, `decisions`, `facts`, and `module-telemetry` use the envelope
`{ contract_version, items, next_cursor }`. `cursor` is an opaque, non-negative
offset supplied by the preceding response; `limit` is 1 through 200.

Responses include an `ETag`. A request with a matching `If-None-Match` returns
`304 Not Modified` and no response body.

## Isolation and extensions

While the session is in `PROXY_MEETING`, Principal/P receives
`403 STUDY2_DATA_NOT_AVAILABLE` for `/utterances`. This prevents delegated
meeting content from crossing the isolation boundary.

Study 1's formal protocol rejects an enabled ReSync flag and any `module_id`.
The Study 1 frontend extension registry has an empty local allowlist; its slot
renders no fallback, generated, or intelligent content while disabled. Any
future allowlisted module must remain local, use this read-only API, and be
added through a versioned contract revision.
