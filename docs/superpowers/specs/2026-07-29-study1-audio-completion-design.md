# Study 1 Audio-Only Completion Design

**Date:** 2026-07-29

**Status:** User-approved design, pending implementation plan

**Target branch:** `codex/study1-audio-completion`

## 1. Purpose

This change closes the nineteen gaps identified by comparing the merged Study 1 system with `Study1_系统开发任务书_v1.1.pdf` while deliberately removing all video requirements. The result is an audio-only Study 1 platform whose experiment flow, Proxy behavior, measurements, event history, exports, and extension contracts are suitable for technical acceptance.

The software delivery includes automated checks, a pilot harness, an operator SOP, integrity reports, and version-freezing tools. Institutional approval, production credentials, and real-person pilot execution remain deployment activities and must not be reported as completed by the software.

## 2. Scope

### 2.1 Included

- Registered three-candidate Hidden Profile tasks with validated atomic facts.
- Immutable, versioned Session protocol configuration.
- Server-enforced pause, termination, phase, role, and material gates.
- Separate individual, tentative, team-final, and individual-final decisions.
- Shared, versioned team decision and follow-up task with three-person confirmation.
- Protocol-fixed Proxy authority and a complete read-only confirmation view.
- A stable audio room across Proxy discussion, handoff, and synchronous discussion.
- Streaming speech processing, deterministic error handling, neutral status updates, barge-in, and complete Agent turn logs.
- Independent audio recordings on a shared UTC and media-relative timeline.
- Reliable review telemetry, Summary failure handling, offline Summary audit, critical markers, and interview replay.
- Reconstructable exports, Study 2 read-only interfaces, privacy controls, data lifecycle support, and release manifests.
- A responsive, English-only meeting UI based on the supplied reference layout.

### 2.2 Explicitly excluded

- Camera permission checks or camera selection.
- Video publication, subscription, display, or recording.
- Video consent fields.
- Automated ReSync analysis or participant-facing intelligent inference.
- Secret researcher input into Proxy speech.
- Claims that IRB approval, real-person pilots, or production service approval have occurred.

## 3. Architectural Boundaries

### 3.1 Platform A

Platform A remains the only experiment orchestrator and the owner of the primary Study 1 database. It owns Sessions, role-bound identities, task definitions, material authorization, protocol versions, phase transitions, submissions, shared team artifacts, review gates, researcher controls, privacy workflow, and final export assembly.

Every write is checked against Session status, current phase, role, and protocol version. A paused, terminated, failed, or completed Session rejects writes unless the action is an explicitly authorized researcher recovery operation.

### 3.2 Media Service B

Platform B owns LiveKit audio, media connections, VAD, streaming ASR, LLM calls, streaming TTS, Proxy lifecycle, audio recording, media metrics, transcripts, Summary generation, and media artifacts. B never changes A's experiment phase or primary database directly. It consumes idempotent commands and returns idempotent events through the existing authenticated internal boundary.

### 3.3 Stable audio room

Each Session has one stable room name for both meeting periods. During `PROXY_MEETING`, only T1, T2, and X receive access. During `HANDOFF`, X is stopped and removed before P receives access. T1 and T2 remain connected. B reports handoff complete only after it observes P connected, X disconnected, and the expected speaking rights.

## 4. Domain Model

### 4.1 Task registry

`study1_task_definition`

- `task_definition_id`
- `task_version`
- `title`
- `candidate_ids`, exactly three unique values
- `status`: `draft`, `validated`, or `retired`
- `content_checksum`
- `created_at`, `created_by`

`study1_task_fact`

- `fact_id`, globally unique within a task version
- `task_definition_id`
- `candidate_id`, constrained to the task's three candidates
- `text`
- `valence`, constrained to the protocol enum
- `information_type`: `shared` or `unique`
- `visible_to_roles`, a non-empty subset of P, T1, and T2

A task can become `validated` only when it has exactly three candidates, every fact references a candidate, all role material views are non-empty, and all uniqueness and visibility constraints pass. Formal Sessions can only use validated tasks.

### 4.2 Immutable Session protocol

The Session stores one canonical configuration snapshot and SHA-256 checksum containing:

- protocol, task, consent, instrument, and UI schema versions;
- all phase durations and minimum review duration;
- laboratory IANA timezone;
- fixed Proxy authority level;
- Proxy model, prompt, and sampling configuration;
- ASR and TTS provider/model versions;
- Summary model, prompt, template, sampling, retry count, and failure policy;
- transcript access policy;
- retention and media access policy;
- feature flags, with ReSync disabled for Study 1;
- frontend, backend, and media build identifiers.

The snapshot becomes immutable when the Session starts. Materials are assigned before start and are included in the checksum. Clone creates a new Session ID, randomization seed, assignments, participants, and invitations while preserving versioned protocol values.

### 4.3 Assignments and materials

Three anonymous participant slots are deterministically permuted onto P, T1, and T2 using the stored randomization seed. Role and fact assignments are append-only records and survive reconnection. One-time links remain role-bound; distributing the links is an operator action and does not expose other roles.

Material reads are permitted only in these phases:

- all roles: `MATERIAL_READING`;
- P: `PROXY_CONFIGURATION`;
- all roles: `HANDOFF`, `SYNC_MEETING`, `FINAL_DECISION`, and `FOLLOWUP_TASK`.

The API applies the same gate as the UI.

### 4.4 Decisions

The decision event model distinguishes:

- `pre_individual`: P, T1, and T2, private and individually locked;
- `tentative_individual`: T1 and T2 before P returns;
- `team_final`: one shared versioned record;
- `final_individual`: P, T1, and T2, private and individually locked.

All candidate choices use registered candidate IDs rather than free text. The protocol captures rationale, confidence, applicable ratings, decision status, actor, server timestamp, instrument version, and source phase.

### 4.5 Shared team artifacts

`team_final` and `followup_task` use a common revision model:

- any current team member can create a new shared draft revision;
- each revision records content, editor, server time, and parent revision;
- P, T1, and T2 confirm the exact revision separately;
- editing creates a new revision and invalidates confirmations on older revisions;
- the artifact locks only after all three confirm the same revision.

The follow-up content has structured resource allocation, ranked actions, and implementation plan fields. A single canonical locked result is exported together with revision history and confirmations.

### 4.6 Formal instruments

Instrument definitions are server-side, versioned, role-specific, and ordered. Formal Sessions always enforce their exact item IDs, response types, ranges, role applicability, and order. The API cannot disable structured validation. Responses remain private and append-only.

## 5. State Machine and Authorization

Every participant and researcher action is represented in an action policy table with allowed statuses, phases, roles, required prerequisites, and emitted events. The same policy drives API checks, readiness, and UI capability DTOs.

- `pause` freezes the deadline and rejects participant submissions, material changes, media access changes, and phase advancement.
- `resume` restores the remaining duration.
- `terminate` revokes new media tokens, stops B, and rejects further participant writes.
- override operations require an enumerated reason code plus a note and produce an immutable event.
- the PRE_VOTE UI locks against `pre_vote`, correcting the current Proxy-completion check.
- all material access and media token issuance are phase-gated on the server.

## 6. Proxy Configuration and Runtime

### 6.1 Configuration

The researcher fixes `authority_level` in the Session condition. P supplies structured goals, priorities, important facts, boundaries, and explicitly selected material IDs. P cannot broaden the fixed authority level.

After submission, P sees a complete read-only rendering of every field, the authorized material titles, authority level, submission time, configuration version, and checksum.

### 6.2 Identity

X is always labelled `AI Proxy for P`. On joining the Proxy meeting, X says a fixed English introduction identifying itself as an AI proxy and stating that it uses only P-authorized information. The introduction is versioned and logged but is not generated by the LLM.

### 6.3 Streaming pipeline

The provider contracts expose partial and final ASR events, LLM token or sentence chunks, and streaming TTS audio frames. Formal mode rejects a provider configuration that lacks the required streaming capability. Mock mode implements deterministic streaming for automated tests.

The pipeline states are `idle`, `listening`, `thinking`, `speaking`, and `technical_issue`. Only these neutral states reach participants.

### 6.4 Agent turn audit

Each attempted turn creates an append-only record before external provider calls begin. It stores:

- `agent_turn_id` and triggering utterance ID;
- ordered context event IDs;
- authorized context snapshot and checksum;
- model, system prompt content/version/checksum, sampling, and provider;
- input and output content;
- ASR, LLM, TTS, total, and first-audio latencies;
- retry attempts, interruption details, status, and structured error code.

T1/T2 private material and the global answer are structurally unavailable to this context builder.

### 6.5 Timeout, retry, and neutral failure

ASR, LLM, and TTS have separately configured timeouts and fixed retry counts. A failed component never creates fabricated speech. B records a component-specific error, sends a technical alert to A, changes X to `technical_issue`, and publishes a neutral English status to participants. Recovery uses the same frozen configuration.

### 6.6 Barge-in

When human speech begins during X playback, B cancels the generation/playback task, calls the audio source queue-clear operation, prevents remaining frames from publishing, and emits a `MEDIA_BARGE_IN` event with precise times and affected turn ID.

## 7. Audio Meeting and UI

### 7.1 Desktop layout

The supplied image is the layout reference, not a source of copy or video behavior.

- Header: Study name, Session identifier, stage rail, connection indicator, and role badge.
- Main left surface: dark audio room with three equal, stable participant seats.
- Main right surface: current phase, progress, private materials, and phase-appropriate task controls.
- Bottom controls: microphone, supported output-device selection, and leave control.

Proxy meeting seat order is `Teammate 1 | AI Proxy for P | Teammate 2`. Synchronous meeting seat order is `Principal | Teammate 1 | Teammate 2`.

Seats use neutral avatars, display names, roles, connection status, and neutral speaking state. They are not styled as camera canvases. Color and motion never imply fact importance, candidate quality, agreement, or correctness.

### 7.2 Responsive layout

Desktop uses a three-seat room plus constrained side panel. Tablet retains stable seat dimensions with a narrower panel. Mobile stacks or horizontally scrolls seats and moves the task panel below the room. Fixed aspect ratios and minimum dimensions prevent state labels from shifting controls.

### 7.3 English-only contract

All Study 1 visible text, API errors shown by the UI, tooltips, aria labels, generated technical statuses, and test fixtures intended for display are English. A source scan rejects CJK characters and known mojibake in `frontend/src/study1`. Research data may still contain participant-entered Unicode text.

### 7.4 Devices and connection

The client performs microphone permission and input-device checks. Output selection uses `setSinkId` where supported and reports capability otherwise. Mute changes the actual local track and emits a server event. Join, leave, device change, mute, reconnect attempt, reconnect success, and reconnect failure are logged.

The client attempts token refresh and room recovery for 30 seconds while retaining role, phase, and local state. Failure produces an English neutral message and researcher alert.

### 7.5 RTC quality

The client samples available WebRTC statistics at a fixed interval and sends packet loss, jitter, RTT, bitrate, and connection state. B adds ASR, LLM, TTS, and first-audio timing. Participant UI shows only neutral connection quality; the researcher console receives technical detail.

## 8. Recording and Timeline

All A and B events use server UTC and include the Session's laboratory timezone. B establishes one room timeline origin and records it in every utterance and media artifact.

P, T1, T2, and X have separate audio tracks. Each manifest entry includes speaker, phase spans, absolute start/end UTC, media-relative start/end, duration, checksum, codec, consent scope, file status, and source runtime. Leading silence or timeline offsets preserve alignment even when a speaker joins late.

Transcript segments retain original ASR text, current effective text, edit flag, speaker, phase, absolute time, relative time, confidence when available, and correction history. Human correction is append-only and never overwrites the original value.

## 9. Summary, Review, and Measurement

### 9.1 Summary structure and provenance

The fixed baseline template contains exactly:

1. Overview
2. Discussion Points
3. Decision Status
4. Open Questions
5. Action Items

Every claim cites transcript segment IDs. The artifact stores complete input transcript version, complete prompt, model, provider, sampling, output, start/end time, latency, retries, validation result, and error.

### 9.2 Failure policy

Summary generation automatically retries the configured number of times with the same frozen configuration. If all attempts fail, A follows the Session's frozen policy: `transcript_only` or `terminate_session`. In `transcript_only`, P sees a neutral technical notice, reviews only the transcript, and must still complete the same reconstruction instrument before handoff. In `terminate_session`, participant writes and media access stop. The researcher may request the same fixed retry with a reason. No interface permits manual replacement Summary text.

### 9.3 Review gate and telemetry

P must submit delegation expectations before Review artifacts become readable. The transcript starts collapsed. P must complete the reconstruction instrument before handoff.

Review telemetry uses Page Visibility, focus/blur, idle detection, scroll range, and IntersectionObserver. It records page entry/exit, active reading intervals, Summary visibility, transcript expand/collapse, scroll ranges, segment visibility duration, replay intervals, and submission. Arbitrary UI activity does not count as reading.

### 9.4 Offline quality audit

Researchers receive a versioned coding form for omission, wrong attribution, hallucination, decision-status error, and action-item error. Each finding binds to Summary sections and transcript segments and records coder, severity, note, and timestamp.

### 9.5 Critical events and interview replay

P, T1, and T2 can mark `confusing`, `unexpected`, `uncomfortable`, or `key_decision` after the meeting, with timestamp/range and reason. Researchers can create invisible observation markers with the same temporal precision.

A deterministic selector produces an interview replay list from participant markers, researcher markers, incidents, handoff, and decision changes. Each item includes configurable pre/post context, synchronized transcript, audio range, source marker, and no automatic interpretation.

## 10. Unified Export and Integrity

The final ZIP contains normalized JSONL/CSV plus media files and manifests for:

- Session and frozen configuration;
- pseudonymous participants, device checks, and consent versions;
- task definitions, facts, assignments, and material authorization;
- phase, meeting, RTC metric, UI, incident, privacy, and override events;
- individual and shared decisions, revision history, and confirmations;
- instruments and responses with item order and versions;
- utterances, corrections, Agent turns, Summary artifacts, and Summary audits;
- critical markers and interview replay lists;
- audio manifests and checksums;
- schema and release manifests;
- integrity report.

The integrity report explicitly lists missing files, timeline gaps, disconnects, provider failures, unclosed recordings, incomplete submissions, unconfirmed shared artifacts, configuration mismatches, consent violations, overrides, and pending deletion actions.

Formal mode refuses Session start or export certification when required build/model/prompt values are `unknown` or when the runtime configuration differs from the frozen Session snapshot.

## 11. Study 2 Compatibility

Authenticated, role-scoped, read-only endpoints expose:

- utterance stream;
- decision events;
- fact registry and utterance-to-fact references;
- Proxy authority and authorized behavior records;
- baseline Summary, transcript, and P review telemetry;
- module telemetry.

The participant shell has a named module slot and Session feature flags. Study 1 fixes `resync_enabled=false`; therefore the slot renders no intelligent analysis. Any future module uses a separate bundle and cannot bypass A's phase or data policies.

## 12. Privacy, Consent, and Data Lifecycle

Consent separately covers audio recording, transcription, UI telemetry, and external Agent/provider processing. Each consent has a version and timestamp. A participant can decline before start. Withdrawal creates an audited disposition request according to the frozen protocol.

Potentially identifying mappings use an identity-vault adapter backed by a separate database connection and application-level authenticated encryption. Analysis tables contain only pseudonymous IDs. Formal mode requires a dedicated vault key and database URL when identity links are used.

Researcher authentication gains explicit scopes for experiment operation, transcript correction, quality audit, raw media access, export, and data management. Raw media replay/download requires an allowlisted scope and emits an access event.

Retention rules define review date, deletion date, and per-category disposition. A controlled purge command deletes or irreversibly anonymizes eligible data while retaining a non-identifying tombstone and audit result. No automatic deletion runs without an approved policy and operator action.

## 13. Researcher Console

The console exposes:

- participant connection and device state;
- current phase, remaining time, pause state, and prerequisites;
- Proxy lifecycle and neutral state;
- true ASR, LLM, TTS, recording, callback, and RTC metric health;
- structured incidents, a stable error-code catalog, and observation markers;
- fixed-config Summary retry;
- reasoned pause, resume, extend, terminate, and override actions;
- Summary quality audit and interview replay;
- integrity status, release manifest, privacy requests, and export controls.

Health is based on probes and recent events, never hard-coded `ready` values.

## 14. Migration and Compatibility

Database changes are additive and versioned. Existing Sessions are marked `legacy_protocol` and remain viewable/exportable but cannot be certified as formal. New formal Sessions require the new task registry and complete configuration.

Existing participant invitation URLs and primary endpoint shapes remain available where their semantics are unchanged. New capability DTOs let the frontend transition without trusting local phase logic. A/B command and event envelopes retain idempotency keys and gain versioned payload fields.

## 15. Testing and Acceptance

Implementation follows red-green-refactor for every behavior.

### 15.1 Automated suites

- Backend unit tests for task validation, immutable config, pause/status gates, role/phase material access, decision separation, shared revision confirmation, formal instruments, privacy scopes, and export integrity.
- Media tests for streaming events, timeout/retry, error logs, fixed introduction, neutral states, barge-in queue clearing, stable-room handoff, recording alignment, and metrics.
- Contract tests proving A and B accept the same versioned command/event schemas and reject stale or mismatched configuration.
- Frontend component tests for the meeting layout, real mute behavior, reconnection, materials, shared confirmation, review telemetry, critical markers, and English-only text.
- End-to-end tests for the complete three-person audio-only protocol, fault paths, Summary fallback, data withdrawal, Study 2 read APIs, and reconstructable export.
- Playwright screenshots and interaction checks at desktop, tablet, and mobile sizes, including non-overlap and long English labels.

### 15.2 Pilot support

The repository includes a deterministic synthetic-audio pilot runner, failure-injection scenarios, a ten-run stress-test results template, a three-device 60-minute stability template, separate templates for three-to-five cognitive/usability pilots and three-to-five complete experiment pilots, an operator SOP, known-issues register, and sign-off checklist. Real people, devices, institutional approval, production WSS/TURN, and production provider credentials remain external acceptance actions.

## 16. Requirement Traceability

| Gap | Design coverage |
|---|---|
| 1. Task and Hidden Profile model | Sections 4.1-4.3 |
| 2. Session freeze | Sections 4.2 and 10 |
| 3. Pause behavior | Section 5 |
| 4. Material phase gate | Sections 4.3 and 5 |
| 5. Initial judgment | Section 4.4 |
| 6. Team and individual final decisions | Sections 4.4-4.5 |
| 7. Shared follow-up | Section 4.5 |
| 8. Proxy confirmation and fixed authority | Section 6.1 |
| 9. Proxy audit and recovery | Sections 6.3-6.5 |
| 10. Proxy identity | Section 6.2 |
| 11. Video requirements | Explicitly removed by Section 2.2 |
| 12. Stable handoff | Sections 3.3 and 7.4 |
| 13. RTC pipeline and quality | Sections 6.3, 6.6, 7.4-7.5 |
| 14. Summary and review | Section 9 |
| 15. Formal instruments | Section 4.6 |
| 16. Markers and replay | Section 9.5 |
| 17. Unified timeline and export | Sections 8 and 10 |
| 18. Study 2 interfaces | Section 11 |
| 19. Privacy and formal acceptance | Sections 12 and 15.2 |
