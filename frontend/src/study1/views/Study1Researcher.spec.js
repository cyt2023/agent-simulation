import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'

import Study1FilePicker from '../components/Study1FilePicker.vue'
import Study1Researcher from './Study1Researcher.vue'
import {
  createMarker,
  createReplayPlan,
  fetchMarkers,
  fetchQualitySnapshot,
  fetchReplayPlans,
  fetchResearcherDashboard,
  fetchMediaStatus,
  getStudy1Identity,
  listStudy1Sessions,
  submitSummaryQa,
} from '../services/study1Api.js'


vi.mock('../services/study1Api.js', () => ({
  addStudy1Incident: vi.fn(),
  completeMockMedia: vi.fn(),
  controlStudy1Session: vi.fn(),
  createStudy1Session: vi.fn(),
  createMarker: vi.fn(),
  createReplayPlan: vi.fn(),
  exportStudy1Data: vi.fn(),
  fetchMarkers: vi.fn(),
  fetchQualitySnapshot: vi.fn(),
  fetchReplayPlans: vi.fn(),
  fetchMediaStatus: vi.fn(),
  fetchResearcherDashboard: vi.fn(),
  getStudy1Identity: vi.fn(),
  issueStudy1MediaCommand: vi.fn(),
  listStudy1Sessions: vi.fn(),
  researcherLogin: vi.fn(),
  submitSummaryQa: vi.fn(),
  transitionPhase: vi.fn(),
  uploadStudy1Materials: vi.fn(),
}))

vi.mock('../services/study1Socket.js', () => ({
  joinStudy1Session: vi.fn(),
  leaveStudy1Session: vi.fn(),
  offStudy1Event: vi.fn(),
  onStudy1Event: vi.fn(),
}))

beforeEach(() => vi.clearAllMocks())

it('marks the unauthenticated sign-in card as centered', () => {
  getStudy1Identity.mockReturnValue(null)
  const wrapper = mount(Study1Researcher)

  expect(wrapper.get('.login').classes()).toContain('login-centered')
  wrapper.unmount()
})

it('uses three English custom material uploaders', async () => {
  getStudy1Identity.mockReturnValue({ role: 'researcher' })
  listStudy1Sessions.mockResolvedValue({ sessions: [] })
  const wrapper = mount(Study1Researcher)
  await flushPromises()

  expect(wrapper.findAllComponents(Study1FilePicker)).toHaveLength(3)
  expect(wrapper.text()).toContain('Choose files')
  wrapper.unmount()
})

it('shows markers, replay, and quality controls after selecting a session', async () => {
  getStudy1Identity.mockReturnValue({ role: 'researcher' })
  listStudy1Sessions.mockResolvedValue({
    sessions: [{ session_id: 'session-1', session_name: 'Alpha', phase: 'REVIEW' }],
  })
  fetchResearcherDashboard.mockResolvedValue({
    phase: 'REVIEW',
    status: 'running',
    ready_to_advance: false,
    remaining_seconds: 240,
    phase_started_at: '2026-07-31T09:00:00Z',
    media_service_status: 'ok',
    artifacts: { summary: 'ready', transcript: 'ready' },
    incident_count: 1,
    participants: [],
    not_submitted: [],
  })
  fetchMediaStatus.mockResolvedValue({
    service_status: 'ok',
    runtime_state: 'READY',
    room_kind: 'proxy_meeting',
    room_name: 'session-1',
    components: {
      recorder: { status: 'healthy' },
      asr: { status: 'healthy' },
      llm: { status: 'healthy' },
      tts: { status: 'healthy' },
      proxy: { status: 'healthy' },
    },
  })
  fetchQualitySnapshot.mockResolvedValue({
    rtc: {
      status: 'ok',
      fresh_participant_count: 3,
      stale_participant_count: 0,
      p50_rtt_ms: 120,
      p95_rtt_ms: 240,
    },
    components: {
      recorder: { status: 'healthy' },
      asr: { status: 'healthy' },
      llm: { status: 'healthy' },
      tts: { status: 'healthy' },
      proxy: { status: 'healthy' },
    },
  })
  fetchMarkers.mockResolvedValue({ markers: [] })
  fetchReplayPlans.mockResolvedValue({ replay_plans: [] })

  const wrapper = mount(Study1Researcher)
  await flushPromises()
  await wrapper.get('select').setValue('session-1')
  await flushPromises()

  expect(fetchResearcherDashboard).toHaveBeenCalledWith('session-1')
  expect(fetchMediaStatus).toHaveBeenCalledWith('session-1')
  expect(fetchQualitySnapshot).toHaveBeenCalledWith('session-1')
  expect(wrapper.text()).toContain('Markers and replay')
  expect(wrapper.text()).toContain('p95 RTT 240 ms')
  wrapper.unmount()
})

it('submits a researcher marker from the audit panel', async () => {
  getStudy1Identity.mockReturnValue({ role: 'researcher' })
  listStudy1Sessions.mockResolvedValue({
    sessions: [{ session_id: 'session-1', session_name: 'Alpha', phase: 'REVIEW' }],
  })
  fetchResearcherDashboard.mockResolvedValue({
    phase: 'REVIEW',
    status: 'running',
    ready_to_advance: false,
    remaining_seconds: 240,
    phase_started_at: '2026-07-31T09:00:00Z',
    media_service_status: 'ok',
    artifacts: { summary: 'ready', transcript: 'ready' },
    incident_count: 1,
    participants: [],
    not_submitted: [],
  })
  fetchMediaStatus.mockResolvedValue({
    service_status: 'ok',
    runtime_state: 'READY',
    room_kind: 'proxy_meeting',
    room_name: 'session-1',
    components: {
      recorder: { status: 'healthy' },
      asr: { status: 'healthy' },
      llm: { status: 'healthy' },
      tts: { status: 'healthy' },
      proxy: { status: 'healthy' },
    },
  })
  fetchQualitySnapshot.mockResolvedValue({
    rtc: {
      status: 'ok',
      fresh_participant_count: 3,
      stale_participant_count: 0,
      p50_rtt_ms: 120,
      p95_rtt_ms: 240,
    },
    components: {
      recorder: { status: 'healthy' },
      asr: { status: 'healthy' },
      llm: { status: 'healthy' },
      tts: { status: 'healthy' },
      proxy: { status: 'healthy' },
    },
  })
  fetchMarkers.mockResolvedValue({ markers: [] })
  fetchReplayPlans.mockResolvedValue({ replay_plans: [] })

  const wrapper = mount(Study1Researcher)
  await flushPromises()
  await wrapper.get('select').setValue('session-1')
  await flushPromises()

  await wrapper.get('[data-test="researcher-marker-type"]').setValue('technical')
  await wrapper.get('[data-test="researcher-marker-start"]').setValue(12)
  await wrapper.get('[data-test="researcher-marker-end"]').setValue(14)
  await wrapper.get('[data-test="researcher-marker-reason"]').setValue('ASR briefly dropped.')
  await wrapper.get('form.audit-form').trigger('submit')
  await flushPromises()

  expect(createMarker).toHaveBeenCalledWith('session-1', {
    type: 'technical',
    start_ms: 12000,
    end_ms: 14000,
    reason: 'ASR briefly dropped.',
    participant_visible: false,
  })
  wrapper.unmount()
})

it('submits a replay plan from selected markers', async () => {
  getStudy1Identity.mockReturnValue({ role: 'researcher' })
  listStudy1Sessions.mockResolvedValue({
    sessions: [{ session_id: 'session-1', session_name: 'Alpha', phase: 'REVIEW' }],
  })
  fetchResearcherDashboard.mockResolvedValue({
    phase: 'REVIEW',
    status: 'running',
    ready_to_advance: false,
    remaining_seconds: 240,
    phase_started_at: '2026-07-31T09:00:00Z',
    media_service_status: 'ok',
    artifacts: { summary: 'ready', transcript: 'ready' },
    incident_count: 1,
    participants: [],
    not_submitted: [],
  })
  fetchMediaStatus.mockResolvedValue({
    service_status: 'ok',
    runtime_state: 'READY',
    room_kind: 'proxy_meeting',
    room_name: 'session-1',
    components: {
      recorder: { status: 'healthy' },
      asr: { status: 'healthy' },
      llm: { status: 'healthy' },
      tts: { status: 'healthy' },
      proxy: { status: 'healthy' },
    },
  })
  fetchQualitySnapshot.mockResolvedValue({
    rtc: {
      status: 'ok',
      fresh_participant_count: 3,
      stale_participant_count: 0,
      p50_rtt_ms: 120,
      p95_rtt_ms: 240,
    },
    components: {
      recorder: { status: 'healthy' },
      asr: { status: 'healthy' },
      llm: { status: 'healthy' },
      tts: { status: 'healthy' },
      proxy: { status: 'healthy' },
    },
  })
  fetchMarkers.mockResolvedValue({
    markers: [
      { marker_id: 'marker-1', type: 'technical', start_ms: 10_000, end_ms: 12_000, reason: 'A' },
      { marker_id: 'marker-2', type: 'unexpected', start_ms: 15_000, end_ms: 18_000, reason: 'B' },
    ],
  })
  fetchReplayPlans.mockResolvedValue({ replay_plans: [] })

  const wrapper = mount(Study1Researcher)
  await flushPromises()
  await wrapper.get('select').setValue('session-1')
  await flushPromises()

  await wrapper.get('[data-test="researcher-replay-marker-ids"]').setValue('marker-1, marker-2')
  await wrapper.get('[data-test="researcher-replay-context"]').setValue(8)
  await wrapper.get('form.replay-form').trigger('submit')
  await flushPromises()

  expect(createReplayPlan).toHaveBeenCalledWith('session-1', {
    marker_ids: ['marker-1', 'marker-2'],
    context_seconds: 8,
  })
  wrapper.unmount()
})

it('submits summary QA ratings from the audit panel', async () => {
  getStudy1Identity.mockReturnValue({ role: 'researcher' })
  listStudy1Sessions.mockResolvedValue({
    sessions: [{ session_id: 'session-1', session_name: 'Alpha', phase: 'REVIEW' }],
  })
  fetchResearcherDashboard.mockResolvedValue({
    phase: 'REVIEW',
    status: 'running',
    ready_to_advance: false,
    remaining_seconds: 240,
    phase_started_at: '2026-07-31T09:00:00Z',
    media_service_status: 'ok',
    artifacts: { summary: 'ready', transcript: 'ready' },
    incident_count: 1,
    participants: [],
    not_submitted: [],
  })
  fetchMediaStatus.mockResolvedValue({
    service_status: 'ok',
    runtime_state: 'READY',
    room_kind: 'proxy_meeting',
    room_name: 'session-1',
    components: {
      recorder: { status: 'healthy' },
      asr: { status: 'healthy' },
      llm: { status: 'healthy' },
      tts: { status: 'healthy' },
      proxy: { status: 'healthy' },
    },
  })
  fetchQualitySnapshot.mockResolvedValue({
    rtc: {
      status: 'ok',
      fresh_participant_count: 3,
      stale_participant_count: 0,
      p50_rtt_ms: 120,
      p95_rtt_ms: 240,
    },
    components: {
      recorder: { status: 'healthy' },
      asr: { status: 'healthy' },
      llm: { status: 'healthy' },
      tts: { status: 'healthy' },
      proxy: { status: 'healthy' },
    },
  })
  fetchMarkers.mockResolvedValue({ markers: [] })
  fetchReplayPlans.mockResolvedValue({ replay_plans: [] })

  const wrapper = mount(Study1Researcher)
  await flushPromises()
  await wrapper.get('select').setValue('session-1')
  await flushPromises()

  await wrapper.get('[data-test="summary-qa-artifact-id"]').setValue('summary-1')
  await wrapper.get('[data-test="summary-qa-omission"]').setValue(true)
  await wrapper.get('[data-test="summary-qa-note"]').setValue('Missed a disagreement.')
  await wrapper.get('form.summary-qa-form').trigger('submit')
  await flushPromises()

  expect(submitSummaryQa).toHaveBeenCalledWith('session-1', 'summary-1', {
    omission_error: true,
    misattribution_error: false,
    hallucination_error: false,
    decision_status_error: false,
    action_item_error: false,
    note: 'Missed a disagreement.',
  })
  wrapper.unmount()
})
