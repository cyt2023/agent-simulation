import { beforeEach, expect, it, vi } from 'vitest'

import {
  confirmSharedArtifactRevision,
  createMarker,
  createReplayPlan,
  createRetentionJob,
  createSharedArtifactRevision,
  createSummaryAction,
  createTaskDefinition,
  executeRetentionJob,
  fetchCurrentInstrument,
  fetchMarkers,
  fetchMediaAccess,
  fetchMediaStatus,
  fetchQualitySnapshot,
  fetchReplayPlans,
  fetchSharedArtifact,
  fetchStudy2Resource,
  fetchTaskDefinition,
  fetchMe,
  listTaskDefinitions,
  reportQualityMetrics,
  researcherLogin,
  replaceTaskDefinition,
  requestStudy1Withdrawal,
  sendReviewEventBatch,
  submitIndividualDecision,
  submitInstrumentResponse,
  submitSummaryQa,
  validateTaskDefinition,
} from './study1Api.js'


beforeEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})


it('can request scoped researcher tokens', async () => {
  const fetchMock = vi.fn(async () => new Response(
    JSON.stringify({ token: 'researcher-token' }),
    { status: 200, headers: { 'content-type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)

  await researcherLogin('researcher-key', ['operate', 'privacy_admin'])

  const body = JSON.parse(fetchMock.mock.calls[0][1].body)
  expect(body).toEqual({
    key: 'researcher-key',
    scopes: ['operate', 'privacy_admin'],
  })
})


it('posts withdrawal requests to the privacy endpoint', async () => {
  const fetchMock = vi.fn(async () => new Response(
    JSON.stringify({ accepted: true }),
    { status: 202, headers: { 'content-type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)

  await requestStudy1Withdrawal('session 1', {
    request_type: 'withdrawal',
    reason: 'Review withdrawal.',
    confirmation: true,
  })

  expect(fetchMock.mock.calls[0][0]).toBe('/api/study1/sessions/session%201/privacy/withdrawal-requests')
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
    request_type: 'withdrawal',
    reason: 'Review withdrawal.',
    confirmation: true,
  })
})


it('posts review telemetry batches to the batch endpoint', async () => {
  const fetchMock = vi.fn(async () => new Response(
    JSON.stringify({ accepted: true }),
    { status: 202, headers: { 'content-type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)

  await sendReviewEventBatch('session-1', {
    visit_id: 'visit-1',
    events: [{ sequence_no: 1, event_type: 'enter' }],
  })

  expect(fetchMock.mock.calls[0][0]).toBe('/api/study1/sessions/session-1/review-events/batch')
})


it('normalizes participant state returned by the authoritative me endpoint', async () => {
  const fetchMock = vi.fn(async () => new Response(
    JSON.stringify({
      identity: { role: 'principal', session_id: 'session-1' },
      session: {
        phase: 'PRE_VOTE',
        phase_version: 2,
        capabilities: { submit_pre_individual: false },
      },
    }),
    { status: 200, headers: { 'content-type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)

  const result = await fetchMe('session-1')

  expect(result.session.capabilities.submit_pre_individual).toBe(false)
  expect(result.session.capabilities.submit_final_decision).toBe(false)
})


it('rejects camera grants returned by the media access endpoint', async () => {
  const fetchMock = vi.fn(async () => new Response(
    JSON.stringify({ publish_sources: ['microphone', 'camera'] }),
    { status: 200, headers: { 'content-type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)

  await expect(fetchMediaAccess('session-1')).rejects.toThrow(/audio-only/i)
})


it('normalizes researcher media status from probe evidence', async () => {
  const fetchMock = vi.fn(async () => new Response(
    JSON.stringify({
      service_status: 'ok',
      runtime_state: 'PROXY_MEETING',
      components: { asr: { status: 'unexpected' } },
      rtc: { status: 'healthy', p50_rtt_ms: 12, p95_rtt_ms: 48, participant_count: 3 },
    }),
    { status: 200, headers: { 'content-type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)

  const result = await fetchMediaStatus('session-1')

  expect(result.components.asr.status).toBe('unknown')
  expect(result.rtc.p95_rtt_ms).toBe(48)
})


it('wraps formal Study 1 participant and researcher endpoints', async () => {
  const fetchMock = vi.fn(async () => new Response(
    JSON.stringify({ ok: true }),
    { status: 200, headers: { 'content-type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)

  await fetchCurrentInstrument('session 1')
  await submitInstrumentResponse('session 1', 'instrument-a', '2.0', [{ item_id: 'q1', value: 4 }])
  await submitIndividualDecision('session 1', 'pre_individual', { candidate_id: 'a' })
  await fetchSharedArtifact('session 1', 'team_final')
  await createSharedArtifactRevision('session 1', 'team_final', {
    parent_revision_id: 'revision-1',
    content: { candidate_id: 'b', rationale: 'Shared rationale' },
  })
  await confirmSharedArtifactRevision('session 1', 'team_final', 'revision-2')
  await fetchMarkers('session 1')
  await createMarker('session 1', { type: 'confusing', start_ms: 0, end_ms: 1000, reason: 'Range was unclear.' })
  await fetchReplayPlans('session 1')
  await createReplayPlan('session 1', { marker_ids: ['marker-1'] })
  await createSummaryAction('session 1', { action: 'retry', reason: 'Probe failure.' })
  await submitSummaryQa('session 1', 'summary-1', { grounded: 5 })
  await reportQualityMetrics('session 1', { rtt_ms: 42 })
  await fetchQualitySnapshot('session 1')
  await createRetentionJob({ session_id: 'session 1', action: 'dry_run' })
  await executeRetentionJob('retention-1', { approved_by: 'researcher' })
  await fetchStudy2Resource('session 1', 'baseline-recap', { cursor: 'abc', limit: 10 })

  expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
    '/api/study1/sessions/session%201/me/instrument',
    '/api/study1/sessions/session%201/me/instrument',
    '/api/study1/sessions/session%201/decisions/pre-individual',
    '/api/study1/sessions/session%201/shared-artifacts/team-final',
    '/api/study1/sessions/session%201/shared-artifacts/team-final/revisions',
    '/api/study1/sessions/session%201/shared-artifacts/team-final/revisions/revision-2/confirm',
    '/api/study1/sessions/session%201/markers',
    '/api/study1/sessions/session%201/markers',
    '/api/study1/sessions/session%201/replay-plans',
    '/api/study1/sessions/session%201/replay-plans',
    '/api/study1/sessions/session%201/summary-actions',
    '/api/study1/sessions/session%201/summary-qa',
    '/api/study1/sessions/session%201/quality-metrics',
    '/api/study1/sessions/session%201/quality',
    '/api/study1/privacy/retention-jobs',
    '/api/study1/privacy/retention-jobs/retention-1/execute',
    '/api/study2/v1/sessions/session%201/baseline-recap?cursor=abc&limit=10',
  ])
})


it('wraps task definition authoring endpoints', async () => {
  const fetchMock = vi.fn(async () => new Response(
    JSON.stringify({ ok: true }),
    { status: 200, headers: { 'content-type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)

  await createTaskDefinition({ title: 'Route choice task' })
  await listTaskDefinitions('active')
  await fetchTaskDefinition('task 1', '2.0')
  await replaceTaskDefinition('task 1', { title: 'Updated task' }, '2.0')
  await validateTaskDefinition('task 1', '2.0')

  expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
    '/api/study1/task-definitions',
    '/api/study1/task-definitions?status=active',
    '/api/study1/task-definitions/task%201?version=2.0',
    '/api/study1/task-definitions/task%201?version=2.0',
    '/api/study1/task-definitions/task%201/validate?version=2.0',
  ])
})
