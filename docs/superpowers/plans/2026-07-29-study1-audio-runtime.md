# Study 1 Audio Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a stable audio-only LiveKit room, streaming Proxy pipeline, deterministic recovery, aligned recordings, quality metrics, and truthful health reporting.

**Architecture:** Freeze an A/B v2 media configuration, separate the persistent recorder connection from the removable X publisher, and persist every turn and component attempt before external calls. All media events share one room clock and flow back to A through the authenticated idempotent callback contract.

**Tech Stack:** FastAPI, SQLAlchemy, asyncio, LiveKit Python SDK, OpenAI streaming APIs, pytest.

---

### Task 1: Freeze the v2 media contract and persistence schema

**Files:**
- Modify: `contracts/study1-media-contract.md`
- Modify: `backend/study1/media_gateway.py`
- Modify: `media_service/app/schemas.py`
- Modify: `media_service/app/config.py`
- Modify: `media_service/app/models.py`
- Modify: `media_service/app/repository.py`
- Create: `media_service/app/media_config.py`
- Create: `media_service/app/schema_migrations.py`
- Test: `media_service/tests/test_media_config.py`
- Test: `media_service/tests/test_schema_migrations.py`

- [ ] **Step 1: Write failing checksum, catalog, and migration tests**

```python
def test_media_config_checksum_must_match_command():
    command = start_proxy_command(media_config_checksum="wrong")
    with pytest.raises(MediaConfigError, match="checksum"):
        FrozenMediaConfig.from_command(command)

def test_agent_turn_is_created_before_provider_attempt(repository):
    turn = repository.begin_agent_turn(turn_start())
    assert turn.status == "started"
    assert turn.context_event_ids
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_media_config.py media_service/tests/test_schema_migrations.py -q`

Expected: frozen config and v2 tables do not exist.

- [ ] **Step 3: Implement v2 configuration and additive schema**

Add `FrozenMediaConfig`, `ProviderPolicy`, `StreamingCapabilities`, and canonical checksum verification. Add schema-versioned rows for room state, phase spans, media config, Agent turns/events, RTC metrics, component health, recording tracks/spans, and Summary attempts. Include all new event names in both A and B catalogs.

- [ ] **Step 4: Run contract, migration, and command tests**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_media_config.py media_service/tests/test_schema_migrations.py media_service/tests/test_commands.py backend/tests/study1/test_http_media_gateway.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add contracts/study1-media-contract.md backend/study1/media_gateway.py media_service/app/schemas.py media_service/app/config.py media_service/app/models.py media_service/app/repository.py media_service/app/media_config.py media_service/app/schema_migrations.py media_service/tests/test_media_config.py media_service/tests/test_schema_migrations.py
git commit -m "feat(media): freeze audio runtime contract"
```

### Task 2: Use one stable room with separate recorder and Proxy connections

**Files:**
- Create: `media_service/app/room_policy.py`
- Modify: `media_service/app/access.py`
- Modify: `media_service/app/livekit_runtime.py`
- Modify: `media_service/app/runtime.py`
- Test: `media_service/tests/test_access.py`
- Test: `media_service/tests/test_livekit_runtime.py`
- Test: `media_service/tests/test_runtime.py`

- [ ] **Step 1: Write failing stable-room tests**

```python
def test_proxy_and_sync_use_same_room_name():
    policy = StableRoomPolicy()
    assert policy.room_name("session-1") == "study1-session-1-audio"

@pytest.mark.asyncio
async def test_disconnecting_proxy_keeps_recorder_connected(runtime):
    await runtime.start_proxy("session-1", 5, config())
    await runtime.disconnect_proxy("session-1")
    assert runtime.connections("session-1").recorder_connected is True
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_access.py media_service/tests/test_livekit_runtime.py media_service/tests/test_runtime.py -q`

Expected: current runtime couples room kind, recorder, and X lifecycle.

- [ ] **Step 3: Implement `StableRoomPolicy` and split connections**

Use `study1-{safe_session_id}-audio` for the full Session. Implement `ensure_session_room`, `connect_recorder`, `connect_proxy_publisher`, `disconnect_proxy`, `close_session_room`, and speaking policy updates. Restrict all publish grants to microphone; do not add camera or video sources.

- [ ] **Step 4: Run room and restart reconciliation tests**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_access.py media_service/tests/test_livekit_runtime.py media_service/tests/test_runtime.py -q`

Expected: all tests pass and restart reconciliation does not duplicate connections.

- [ ] **Step 5: Commit**

```powershell
git add media_service/app/room_policy.py media_service/app/access.py media_service/app/livekit_runtime.py media_service/app/runtime.py media_service/tests/test_access.py media_service/tests/test_livekit_runtime.py media_service/tests/test_runtime.py
git commit -m "feat(media): keep one stable audio room"
```

### Task 3: Make handoff an observed barrier

**Files:**
- Modify: `media_service/app/runtime.py`
- Modify: `media_service/app/commands.py`
- Modify: `media_service/app/repository.py`
- Modify: `backend/study1/services.py`
- Test: `media_service/tests/test_runtime.py`

- [ ] **Step 1: Write failing handoff tests**

```python
@pytest.mark.asyncio
async def test_handoff_waits_for_principal_and_proxy_absence(coordinator):
    await coordinator.begin_handoff("session-1", 9)
    assert not coordinator.events("HANDOFF_COMPLETE")
    await coordinator.participant_state_changed("session-1", "principal", "connected")
    assert not coordinator.events("HANDOFF_COMPLETE")
    await coordinator.participant_state_changed("session-1", "proxy", "disconnected")
    assert len(coordinator.events("HANDOFF_COMPLETE")) == 1
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_runtime.py -q -k handoff`

Expected: handoff currently completes immediately after room creation.

- [ ] **Step 3: Implement `HandoffBarrier` and speaking rights**

Track expected human connections, X absence, and applied speaking policy. Ending the Proxy period finalizes artifacts and removes X while retaining recorder/T1/T2. Emit `HANDOFF_COMPLETE` once, with participant join time, X stop time, room, and speaking-rights snapshot.

- [ ] **Step 4: Run runtime and A callback tests**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_runtime.py backend/tests/study1/test_media_artifacts.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add media_service/app/runtime.py media_service/app/commands.py media_service/app/repository.py backend/study1/services.py media_service/tests/test_runtime.py
git commit -m "feat(media): complete handoff from observed participants"
```

### Task 4: Introduce real streaming provider contracts

**Files:**
- Modify: `media_service/app/providers/base.py`
- Modify: `media_service/app/providers/mock.py`
- Modify: `media_service/app/providers/factory.py`
- Modify: `media_service/app/providers/openai.py`
- Create: `media_service/app/providers/openai_realtime.py`
- Create: `media_service/app/audio_format.py`
- Test: `media_service/tests/test_streaming_providers.py`
- Test: `media_service/tests/test_openai_realtime_provider.py`

- [ ] **Step 1: Write failing partial-before-final and capability tests**

```python
@pytest.mark.asyncio
async def test_asr_stream_emits_partial_before_final(provider):
    session = await provider.open_asr_session(utterance_id="u1")
    await session.push(PcmFrame(b"frame", 16000, 1, 1))
    await session.commit()
    events = [event async for event in session.events()]
    assert [event.kind for event in events] == ["partial", "final"]

def test_formal_mode_rejects_batch_asr(factory):
    with pytest.raises(ProviderCapabilityError):
        factory.create(formal=True, asr_model="whisper-1")
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_streaming_providers.py media_service/tests/test_openai_realtime_provider.py -q`

Expected: provider API only accepts a complete utterance buffer.

- [ ] **Step 3: Implement streaming ASR/LLM/TTS interfaces**

Add `PcmFrame`, `AsrEvent`, `StreamingAsrSession`, `LlmDelta`, `TtsFrame`, and `ProviderCapabilities`. Use an injectable transport for OpenAI realtime transcription tests. Preserve a legacy batch adapter only for non-formal development.

- [ ] **Step 4: Run all provider tests**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_streaming_providers.py media_service/tests/test_openai_realtime_provider.py media_service/tests/test_proxy_pipeline.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add media_service/app/providers media_service/app/audio_format.py media_service/tests/test_streaming_providers.py media_service/tests/test_openai_realtime_provider.py
git commit -m "feat(media): stream ASR LLM and TTS providers"
```

### Task 5: Persist Agent turns, neutral states, identity, and deterministic failures

**Files:**
- Create: `media_service/app/agent_turns.py`
- Create: `media_service/app/context_builder.py`
- Create: `media_service/app/proxy_state.py`
- Create: `media_service/app/announcements.py`
- Create: `media_service/app/provider_execution.py`
- Create: `media_service/app/errors.py`
- Create: `media_service/app/streaming_pipeline.py`
- Modify: `media_service/app/pipeline.py`
- Modify: `media_service/app/audio_router.py`
- Modify: `media_service/app/main.py`
- Test: `media_service/tests/test_agent_turns.py`
- Test: `media_service/tests/test_fixed_introduction.py`
- Test: `media_service/tests/test_pipeline_failures.py`

- [ ] **Step 1: Write failing ledger, introduction, and retry tests**

```python
@pytest.mark.asyncio
async def test_fixed_introduction_never_calls_llm(pipeline, fake_llm):
    await pipeline.start_session("s1", config())
    assert fake_llm.calls == []
    assert pipeline.turns("s1")[0].turn_kind == "fixed_introduction"

@pytest.mark.asyncio
async def test_llm_exhaustion_records_error_and_no_audio(pipeline):
    pipeline.llm.fail_with(TimeoutError())
    await pipeline.process_final_utterance(utterance())
    turn = pipeline.last_turn()
    assert turn.error_code == "LLM_TIMEOUT"
    assert pipeline.published_audio == []
    assert pipeline.proxy_state == "technical_issue"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_agent_turns.py media_service/tests/test_fixed_introduction.py media_service/tests/test_pipeline_failures.py -q`

Expected: complete ledger, fixed introduction, and structured retries are missing.

- [ ] **Step 3: Implement the audited streaming pipeline**

Begin the Agent ledger before providers, store ordered context IDs and full authorized snapshots, publish only neutral states, validate the complete LLM response before TTS, and execute component-specific timeout/retry policies. TTS may retry only before its first published frame. Use a versioned fixed English self-introduction.

- [ ] **Step 4: Run pipeline, Summary, and callback tests**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_agent_turns.py media_service/tests/test_fixed_introduction.py media_service/tests/test_pipeline_failures.py media_service/tests/test_proxy_pipeline.py media_service/tests/test_transcript_summary.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add media_service/app/agent_turns.py media_service/app/context_builder.py media_service/app/proxy_state.py media_service/app/announcements.py media_service/app/provider_execution.py media_service/app/errors.py media_service/app/streaming_pipeline.py media_service/app/pipeline.py media_service/app/audio_router.py media_service/app/main.py media_service/tests/test_agent_turns.py media_service/tests/test_fixed_introduction.py media_service/tests/test_pipeline_failures.py
git commit -m "feat(media): audit and recover proxy turns"
```

### Task 6: Guarantee barge-in clears queued audio

**Files:**
- Create: `media_service/app/playback.py`
- Modify: `media_service/app/livekit_runtime.py`
- Modify: `media_service/app/audio_router.py`
- Modify: `media_service/app/streaming_pipeline.py`
- Test: `media_service/tests/test_audio_router.py`
- Test: `media_service/tests/test_livekit_runtime.py`

- [ ] **Step 1: Write a failing late-frame regression**

```python
@pytest.mark.asyncio
async def test_barge_in_clears_queue_and_rejects_late_frames(playback):
    generation = playback.begin("turn-1")
    await playback.interrupt(generation)
    await playback.publish(generation, b"late")
    assert playback.audio_source.clear_queue.await_count == 1
    assert playback.audio_source.capture_frame.await_count == 0
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_audio_router.py media_service/tests/test_livekit_runtime.py -q -k 'barge or queue or late'`

Expected: cancel does not clear the LiveKit source queue.

- [ ] **Step 3: Implement generation-aware playback cancellation**

Track playback generation and turn ID. On VAD speech-start: mark interrupted, cancel generation/TTS, call `AudioSource.clear_queue`, reject late frames, emit one `MEDIA_BARGE_IN`, then return to listening.

- [ ] **Step 4: Run barge-in and pipeline suites**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_audio_router.py media_service/tests/test_livekit_runtime.py media_service/tests/test_proxy_pipeline.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add media_service/app/playback.py media_service/app/livekit_runtime.py media_service/app/audio_router.py media_service/app/streaming_pipeline.py media_service/tests/test_audio_router.py media_service/tests/test_livekit_runtime.py
git commit -m "fix(media): clear proxy audio on barge in"
```

### Task 7: Align recordings and transcripts to one room clock

**Files:**
- Create: `media_service/app/timeline.py`
- Modify: `media_service/app/audio.py`
- Modify: `media_service/app/audio_router.py`
- Modify: `media_service/app/repository.py`
- Modify: `media_service/app/export.py`
- Test: `media_service/tests/test_timeline.py`
- Test: `media_service/tests/test_aligned_recording.py`

- [ ] **Step 1: Write failing late-join and manifest tests**

```python
def test_late_join_track_keeps_room_offset(recorder, room_clock):
    recorder.start_track("principal", room_relative_ms=90_000)
    manifest = recorder.finish_track("principal")
    assert manifest.room_start_ms == 90_000
    assert manifest.started_at_utc == room_clock.to_utc(90_000)
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_timeline.py media_service/tests/test_aligned_recording.py -q`

Expected: recordings have duration/checksum but no shared origin or spans.

- [ ] **Step 3: Implement `RoomClock` and aligned track manifests**

Persist one origin UTC/monotonic pair, recording offsets and phase spans, original/effective transcript text, absolute and relative times, codec/sample rate, consent scope, track/runtime IDs, duration, checksum, and file status. Build export manifests from persisted recording rows rather than globbing WAV files.

- [ ] **Step 4: Run audio, repository, and export tests**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_timeline.py media_service/tests/test_aligned_recording.py media_service/tests/test_audio_router.py media_service/tests/test_repository.py media_service/tests/test_outbox_export.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add media_service/app/timeline.py media_service/app/audio.py media_service/app/audio_router.py media_service/app/repository.py media_service/app/export.py media_service/tests/test_timeline.py media_service/tests/test_aligned_recording.py
git commit -m "feat(media): align audio artifacts to one clock"
```

### Task 8: Add RTC metrics, truthful health, and media end-to-end tests

**Files:**
- Create: `media_service/app/rtc_metrics.py`
- Create: `media_service/app/health.py`
- Modify: `backend/study1/media_gateway.py`
- Modify: `backend/study1/services.py`
- Modify: `backend/study1/routes.py`
- Modify: `media_service/app/main.py`
- Modify: `media_service/app/repository.py`
- Modify: `media_service/app/export.py`
- Test: `media_service/tests/test_rtc_metrics.py`
- Test: `media_service/tests/test_health.py`
- Test: `media_service/tests/test_audio_protocol_e2e.py`

- [ ] **Step 1: Write failing stale-health tests**

```python
def test_asr_health_is_unknown_without_probe(health_service):
    assert health_service.snapshot()["asr"]["status"] == "unknown"

def test_failed_probe_is_never_reported_ready(health_service):
    health_service.record_failure("asr", "ASR_PROVIDER_ERROR")
    assert health_service.snapshot()["asr"]["status"] == "failed"
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest -p no:cacheprovider media_service/tests/test_rtc_metrics.py media_service/tests/test_health.py -q`

Expected: status currently hard-codes ASR ready and recording active.

- [ ] **Step 3: Implement metrics aggregation and probes**

Persist packet loss, jitter, RTT, bitrate, connection state, observed time, and participant. Add an authenticated A endpoint that injects the participant identity and proxies client metric batches to B. Aggregate provider last success/error, consecutive failures, and p50/p95 latency. Add `/readyz` probes and make `/status` report `unknown`, `healthy`, `degraded`, or `failed` from evidence.

- [ ] **Step 4: Run the complete media suite**

Run: `python -m pytest -p no:cacheprovider media_service/tests -q`

Expected: all media tests pass, including synthetic audio Proxy-to-handoff-to-sync export.

- [ ] **Step 5: Commit**

```powershell
git add backend/study1/media_gateway.py backend/study1/services.py backend/study1/routes.py media_service/app/rtc_metrics.py media_service/app/health.py media_service/app/main.py media_service/app/repository.py media_service/app/export.py media_service/tests/test_rtc_metrics.py media_service/tests/test_health.py media_service/tests/test_audio_protocol_e2e.py
git commit -m "feat(media): report audio quality and real health"
```
