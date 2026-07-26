# Study 1 Media Service (B)

This service owns audio meeting infrastructure only: LiveKit rooms, microphone
audio, per-track recording, timestamped ASR, one server-side Proxy participant,
LLM/TTS, transcript and neutral-summary artifacts, callbacks, and media export.
It does not own Session roles, experiment phases, voting, questionnaires, or
the primary Study 1 database.

## Local stack

Set unique values in `.env` for `STUDY1_INTERNAL_API_KEY`,
`A_TO_B_SERVICE_TOKEN`, `MEDIA_DATABASE_PASSWORD`, `LIVEKIT_API_KEY`, and
`LIVEKIT_API_SECRET`, then run:

The two service tokens and `LIVEKIT_API_SECRET` must each be at least 32
characters. Placeholder values are rejected at startup, and Compose has no
fallback media credentials.

```powershell
docker compose up --build postgres livekit media-service backend frontend
```

If the PostgreSQL volume predates B, the init script will not run again. Create
the `study1_media` role/schema manually or recreate only the local development
volume when its contents are disposable.

Use `MEDIA_PROVIDER=mock` for deterministic integration tests. For OpenAI set
`MEDIA_PROVIDER=openai` and `OPENAI_API_KEY`; for Azure set
`MEDIA_PROVIDER=azure`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and the
deployment environment variables in `.env.example`.

## Production RTC

`LIVEKIT_PUBLIC_URL` must be a browser-reachable `wss://` endpoint. Terminate
TLS at a reverse proxy/load balancer and configure LiveKit's advertised IP plus
TURN for networks that cannot reach the UDP range. Do not expose B's port 8000;
only A and B share the service token. B's PostgreSQL user must retain access to
`study1_media` only and must not gain access to `humanagent_collab`.

The Sync room includes a hidden subscribe-only B recorder. It receives
P/T1/T2 microphone tracks for per-runtime WAV recording and ASR but cannot
publish media. Neutral summaries are rendered with transcript segment
citations; invalid or persuasive output is retried once under the same frozen
conditions and then fails closed.

## Verification

```powershell
python -m pytest -p no:cacheprovider media_service\tests -q
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest -p no:cacheprovider backend\tests\study1 -q
npm --prefix frontend test -- --run
npm --prefix frontend run build
docker compose config --quiet
```
