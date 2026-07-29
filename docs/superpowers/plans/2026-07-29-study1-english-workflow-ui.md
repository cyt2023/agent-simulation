# Study 1 English Workflow UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved English-only audio meeting layout and complete participant/researcher workflows using server-provided capabilities and canonical records.

**Architecture:** Keep one participant shell mounted through the meeting lifecycle, move LiveKit connection ownership into a composable, and compose the reference layout from focused seat, control, material, task, review, and researcher panels. No component renders or requests video.

**Tech Stack:** Vue 3 Composition API, LiveKit client, Lucide icons, Vitest, Vue Test Utils, Playwright.

Run `npm.cmd` and `npx playwright` commands from `frontend/`; run Git commands from the repository root.

---

### Task 1: Expand the typed frontend API and capability contract

**Files:**
- Modify: `frontend/src/study1/services/study1Api.js`
- Modify: `frontend/src/study1/services/mediaControls.js`
- Create: `frontend/src/study1/services/study1Contracts.js`
- Test: `frontend/src/study1/services/study1Contracts.spec.js`

- [ ] **Step 1: Write failing normalization tests**

```javascript
it('normalizes server capabilities without inferring them from phase', () => {
  const value = normalizeParticipantState({ phase: 'PRE_VOTE', capabilities: { submit_pre_individual: false } })
  expect(value.capabilities.submit_pre_individual).toBe(false)
})

it('rejects video media sources', () => {
  expect(() => normalizeMediaAccess({ publish_sources: ['microphone', 'camera'] })).toThrow(/audio-only/)
})
```

- [ ] **Step 2: Run and verify RED**

Run: `npm.cmd test -- --run src/study1/services/study1Contracts.spec.js`

Expected: contract normalizers and new API calls do not exist.

- [ ] **Step 3: Implement API methods and normalizers**

Add task/instrument, individual decision, shared artifact revision/confirmation, review event batch, markers/replay, Summary QA, quality, privacy, integrity, and Study 2 API methods. Normalize capabilities and reject camera/video sources at the UI boundary.

- [ ] **Step 4: Run service tests**

Run: `npm.cmd test -- --run src/study1/services`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/study1/services
git commit -m "feat(frontend): consume formal Study 1 contracts"
```

### Task 2: Keep one stable audio connection across meeting phases

**Files:**
- Create: `frontend/src/study1/composables/useStableAudioSession.js`
- Create: `frontend/src/study1/composables/useStableAudioSession.spec.js`
- Create: `frontend/src/study1/services/livekitStatsAdapter.js`
- Modify: `frontend/src/study1/views/Study1Participant.vue`
- Modify: `frontend/src/study1/components/Study1VoiceRoom.vue`
- Test: `frontend/src/study1/components/Study1VoiceRoom.spec.js`

- [ ] **Step 1: Write failing continuity and reconnect tests**

```javascript
it('keeps T1 connected while phase moves from proxy meeting through handoff to sync', async () => {
  const audio = createStableAudioHarness({ role: 'teammate_1' })
  await audio.enterPhase('PROXY_MEETING')
  await audio.enterPhase('TENTATIVE_DECISION')
  await audio.enterPhase('HANDOFF')
  await audio.enterPhase('SYNC_MEETING')
  expect(audio.room.disconnect).not.toHaveBeenCalled()
})

it('stops recovery after thirty seconds and reports failure', async () => {
  const audio = createStableAudioHarness({ reconnectFails: true })
  await audio.advanceTimersByTimeAsync(30_000)
  expect(audio.state.value).toBe('failed')
})
```

- [ ] **Step 2: Run and verify RED**

Run: `npm.cmd test -- --run src/study1/composables/useStableAudioSession.spec.js src/study1/components/Study1VoiceRoom.spec.js`

Expected: room ownership currently lives in the phase component and disconnects on unmount.

- [ ] **Step 3: Implement the stable controller**

Own the single `Room`, device selection, mute state, token refresh, participant map, Proxy attributes, connection recovery, telemetry, and teardown in `useStableAudioSession`. Keep it mounted in `Study1Participant`. P joins only in HANDOFF; T1/T2 remain connected through intermediate forms. Use `setSinkId` only when supported.

- [ ] **Step 4: Run audio component tests**

Run: `npm.cmd test -- --run src/study1/composables/useStableAudioSession.spec.js src/study1/components/Study1VoiceRoom.spec.js src/study1/components/Study1DeviceCheck.spec.js`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/study1/composables frontend/src/study1/services/livekitStatsAdapter.js frontend/src/study1/views/Study1Participant.vue frontend/src/study1/components/Study1VoiceRoom.vue frontend/src/study1/components/Study1VoiceRoom.spec.js
git commit -m "feat(frontend): preserve the Study 1 audio session"
```

### Task 3: Build the reference audio meeting workspace

**Files:**
- Create: `frontend/src/study1/components/Study1MeetingWorkspace.vue`
- Create: `frontend/src/study1/components/Study1MeetingWorkspace.spec.js`
- Create: `frontend/src/study1/components/ParticipantSeat.vue`
- Create: `frontend/src/study1/components/MeetingControls.vue`
- Create: `frontend/src/study1/components/StudyTaskPanel.vue`
- Modify: `frontend/src/study1/components/PhaseHeader.vue`
- Modify: `frontend/src/study1/components/Study1VoiceRoom.vue`
- Modify: `frontend/src/study1/views/Study1Participant.vue`

- [ ] **Step 1: Write failing layout and seat-order tests**

```javascript
it('renders T1 Proxy T2 in the delegated discussion', () => {
  const wrapper = mountWorkspace({ phase: 'PROXY_MEETING', role: 'teammate_1' })
  expect(wrapper.findAll('[data-test="participant-seat"]').map(node => node.text())).toEqual(
    expect.arrayContaining(['Teammate 1', 'AI Proxy for P', 'Teammate 2'])
  )
})

it('never renders camera controls or video elements', () => {
  const wrapper = mountWorkspace({ phase: 'SYNC_MEETING', role: 'principal' })
  expect(wrapper.find('video').exists()).toBe(false)
  expect(wrapper.text()).not.toMatch(/camera|video/i)
})
```

- [ ] **Step 2: Run and verify RED**

Run: `npm.cmd test -- --run src/study1/components/Study1MeetingWorkspace.spec.js`

Expected: the workspace components do not exist.

- [ ] **Step 3: Implement the responsive workspace**

Match the approved composition: header and stage rail; dark three-seat audio room; light right-side phase/material/task panel; fixed bottom controls. Show neutral avatars and only `Listening`, `Thinking`, `Speaking`, `Technical issue`, connection, and mute states. Use stable dimensions and no importance-signalling color or animation.

- [ ] **Step 4: Run workspace and participant tests**

Run: `npm.cmd test -- --run src/study1/components/Study1MeetingWorkspace.spec.js src/study1/components/Study1VoiceRoom.spec.js`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/study1/components/Study1MeetingWorkspace.vue frontend/src/study1/components/Study1MeetingWorkspace.spec.js frontend/src/study1/components/ParticipantSeat.vue frontend/src/study1/components/MeetingControls.vue frontend/src/study1/components/StudyTaskPanel.vue frontend/src/study1/components/PhaseHeader.vue frontend/src/study1/components/Study1VoiceRoom.vue frontend/src/study1/views/Study1Participant.vue
git commit -m "feat(frontend): build the audio meeting workspace"
```

### Task 4: Render canonical tasks, instruments, and shared team artifacts

**Files:**
- Create: `frontend/src/study1/components/InstrumentPhase.vue`
- Create: `frontend/src/study1/components/SharedArtifactPhase.vue`
- Create: `frontend/src/study1/components/SharedArtifactPhase.spec.js`
- Modify: `frontend/src/study1/components/VotePhase.vue`
- Modify: `frontend/src/study1/components/SurveyPhase.vue`
- Modify: `frontend/src/study1/components/ProxyConfigPhase.vue`
- Modify: `frontend/src/study1/components/MaterialPhase.vue`
- Modify: `frontend/src/study1/views/Study1Participant.vue`
- Create: `frontend/src/study1/views/Study1Participant.spec.js`

- [ ] **Step 1: Write failing canonical-choice and confirmation tests**

```javascript
it('uses the three registered candidates rather than free text', () => {
  const wrapper = mountVote({ candidates: candidates() })
  expect(wrapper.findAll('input[type="radio"]')).toHaveLength(3)
  expect(wrapper.find('input[type="text"]').exists()).toBe(false)
})

it('shows all three confirmations and resets them after a new revision', async () => {
  const wrapper = mountSharedArtifact({ revision: lockedDraft(), confirmations: confirmations() })
  await wrapper.vm.edit({ candidate_id: 'b', rationale: 'new' })
  expect(wrapper.text()).toContain('0 of 3 confirmed')
})
```

- [ ] **Step 2: Run and verify RED**

Run: `npm.cmd test -- --run src/study1/components/SharedArtifactPhase.spec.js src/study1/components/ProxyConfigPhase.spec.js`

Expected: decisions are free text and team work is three independent forms.

- [ ] **Step 3: Implement server-driven forms**

Render current ordered instrument definitions and registered candidates. Separate team-final from private final decisions. Implement shared revision editing and three confirmations for team final and follow-up. Make Proxy authority read-only and render the complete locked configuration with checksum and authorized material titles.

- [ ] **Step 4: Run participant workflow tests**

Run: `npm.cmd test -- --run src/study1/components src/study1/views/Study1Participant.spec.js`

Expected: all available participant tests pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/study1/components/InstrumentPhase.vue frontend/src/study1/components/SharedArtifactPhase.vue frontend/src/study1/components/SharedArtifactPhase.spec.js frontend/src/study1/components/VotePhase.vue frontend/src/study1/components/SurveyPhase.vue frontend/src/study1/components/ProxyConfigPhase.vue frontend/src/study1/components/MaterialPhase.vue frontend/src/study1/views/Study1Participant.vue frontend/src/study1/views/Study1Participant.spec.js
git commit -m "feat(frontend): complete formal participant tasks"
```

### Task 5: Add reliable Review telemetry and post-session markers

**Files:**
- Create: `frontend/src/study1/composables/useReviewTelemetry.js`
- Create: `frontend/src/study1/composables/useReviewTelemetry.spec.js`
- Create: `frontend/src/study1/components/MarkerDialog.vue`
- Create: `frontend/src/study1/components/PostSessionMarkers.vue`
- Create: `frontend/src/study1/components/PostSessionMarkers.spec.js`
- Modify: `frontend/src/study1/components/ReviewPhase.vue`
- Modify: `frontend/src/study1/components/ReviewPhase.spec.js`
- Modify: `frontend/src/study1/views/Study1Participant.vue`

- [ ] **Step 1: Write failing focus/visibility and marker tests**

```javascript
it('does not count hidden-tab time as active reading', async () => {
  const telemetry = createTelemetryHarness()
  telemetry.enter()
  telemetry.setVisibility('hidden')
  await telemetry.advance(20_000)
  expect(telemetry.activeSeconds()).toBe(0)
})

it.each(['confusing', 'unexpected', 'uncomfortable', 'key_decision'])('submits %s markers', async type => {
  const wrapper = mountMarkers()
  await wrapper.vm.submit({ type, start_utc: now(), end_utc: now(), note: 'Reason' })
  expect(api.createMarker).toHaveBeenCalledWith(expect.objectContaining({ type }))
})
```

- [ ] **Step 2: Run and verify RED**

Run: `npm.cmd test -- --run src/study1/composables/useReviewTelemetry.spec.js src/study1/components/PostSessionMarkers.spec.js src/study1/components/ReviewPhase.spec.js`

Expected: reading time is wall-clock mount duration and markers lack typed ranges.

- [ ] **Step 3: Implement batched reliable telemetry and markers**

Use Page Visibility, focus/blur, idle threshold, IntersectionObserver, scroll ranges, sequence numbers, offline queueing, and batch resend. Keep transcript collapsed by default. Add typed participant markers with time/range and reason after the meeting.

- [ ] **Step 4: Run Review and marker tests**

Run: `npm.cmd test -- --run src/study1/composables/useReviewTelemetry.spec.js src/study1/components/ReviewPhase.spec.js src/study1/components/PostSessionMarkers.spec.js`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/study1/composables/useReviewTelemetry.js frontend/src/study1/composables/useReviewTelemetry.spec.js frontend/src/study1/components/MarkerDialog.vue frontend/src/study1/components/PostSessionMarkers.vue frontend/src/study1/components/PostSessionMarkers.spec.js frontend/src/study1/components/ReviewPhase.vue frontend/src/study1/components/ReviewPhase.spec.js frontend/src/study1/views/Study1Participant.vue
git commit -m "feat(frontend): measure review and collect markers"
```

### Task 6: Complete the researcher console and visual acceptance

**Files:**
- Create: `frontend/src/study1/components/MediaHealthPanel.vue`
- Create: `frontend/src/study1/components/SummaryQaPanel.vue`
- Create: `frontend/src/study1/components/ResearcherReplayList.vue`
- Create: `frontend/src/study1/components/ProtocolIntegrityPanel.vue`
- Modify: `frontend/src/study1/views/Study1Researcher.vue`
- Modify: `frontend/src/study1/views/Study1Researcher.spec.js`
- Modify: `frontend/src/study1/englishOnly.spec.js`
- Create: `frontend/e2e/study1-audio-workspace.spec.js`

- [ ] **Step 1: Write failing health, English, and layout tests**

```javascript
it('shows unknown rather than ready when no ASR probe exists', () => {
  const wrapper = mountResearcher({ health: { asr: { status: 'unknown' } } })
  expect(wrapper.text()).toContain('Unknown')
  expect(wrapper.text()).not.toContain('Ready')
})

it('contains no CJK or known mojibake in Study 1 display sources', () => {
  expect(scanStudy1DisplaySources()).toEqual([])
})
```

- [ ] **Step 2: Run and verify RED**

Run: `npm.cmd test -- --run src/study1/views/Study1Researcher.spec.js src/study1/englishOnly.spec.js`

Expected: full QA/replay/integrity panels and strict scan are missing.

- [ ] **Step 3: Implement researcher panels and Playwright coverage**

Show probe-based component health, RTC p50/p95, error codes, Summary attempts/fixed retry/QA, invisible markers, deterministic replay, privacy/integrity state, and release manifest. Add desktop/tablet/mobile screenshots and assertions for seat order, sidebar, no overlap, stable controls, and no video elements.

- [ ] **Step 4: Run frontend tests and build**

Run: `npm.cmd test -- --run`

Run: `npm.cmd run build`

Expected: tests and production build pass.

- [ ] **Step 5: Run Playwright**

Run: `npx playwright test frontend/e2e/study1-audio-workspace.spec.js`

Expected: desktop, tablet, and mobile checks pass with nonblank screenshots.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/study1 frontend/e2e/study1-audio-workspace.spec.js
git commit -m "feat(frontend): complete researcher and audio UI"
```
