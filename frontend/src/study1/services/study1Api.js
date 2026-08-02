import {
  normalizeMediaAccess,
  normalizeParticipantState,
  normalizeResearcherMediaStatus,
} from './study1Contracts.js'

const TOKEN_KEY = 'study1_auth_token'
const IDENTITY_KEY = 'study1_identity'

export function getStudy1Token() {
  return sessionStorage.getItem(TOKEN_KEY) || ''
}

export function getStudy1Identity() {
  try {
    return JSON.parse(sessionStorage.getItem(IDENTITY_KEY) || 'null')
  } catch {
    return null
  }
}

export function clearStudy1Auth() {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(IDENTITY_KEY)
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {})
  const token = getStudy1Token()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(path, { ...options, headers })
  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await response.json() : null
  if (!response.ok) {
    const error = new Error(data?.message || data?.error || `Request failed (${response.status})`)
    error.status = response.status
    error.data = data
    throw error
  }
  return data
}

export async function exchangeInvite(token) {
  const result = await request(`/api/study1/invites/${encodeURIComponent(token)}/exchange`, {
    method: 'POST',
  })
  sessionStorage.setItem(TOKEN_KEY, result.token)
  sessionStorage.setItem(IDENTITY_KEY, JSON.stringify(result.identity))
  return result
}

export function fetchMe(sessionId) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/me`)
    .then(result => ({
      ...result,
      session: normalizeParticipantState(result.session || {}),
    }))
}

export function fetchMyMaterials(sessionId) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/me/materials`)
}

export async function fetchStudy1Recording(sessionId, recordingId) {
  const token = getStudy1Token()
  const response = await fetch(
    `/api/study1/sessions/${encodeURIComponent(sessionId)}/recordings/${encodeURIComponent(recordingId)}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  )
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data?.message || `Recording replay failed (${response.status})`)
  }
  return response.blob()
}

export function createSubmission(sessionId, type, payload, instrumentVersion = '1.0') {
  return request(
    `/api/study1/sessions/${encodeURIComponent(sessionId)}/submissions/${encodeURIComponent(type)}`,
    {
      method: 'POST',
      body: JSON.stringify({
        instrument_version: instrumentVersion,
        payload,
        client_timestamp: new Date().toISOString(),
      }),
    },
  )
}

export async function researcherLogin(key, scopes = null) {
  const body = { key }
  if (Array.isArray(scopes) && scopes.length) body.scopes = scopes
  const result = await request('/api/study1/auth/researcher', {
    method: 'POST',
    body: JSON.stringify(body),
  })
  sessionStorage.setItem(TOKEN_KEY, result.token)
  sessionStorage.setItem(
    IDENTITY_KEY,
    JSON.stringify({ participant_id: 'researcher', role: 'researcher', session_id: null }),
  )
  return result
}

function formalSegment(value) {
  return encodeURIComponent(String(value || '').replaceAll('_', '-'))
}

export function createTaskDefinition(payload) {
  return request('/api/study1/task-definitions', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function listTaskDefinitions(status = null) {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return request(`/api/study1/task-definitions${query}`)
}

export function fetchTaskDefinition(taskDefinitionId, version = null) {
  const query = version ? `?version=${encodeURIComponent(version)}` : ''
  return request(`/api/study1/task-definitions/${encodeURIComponent(taskDefinitionId)}${query}`)
}

export function replaceTaskDefinition(taskDefinitionId, payload, version = null) {
  const query = version ? `?version=${encodeURIComponent(version)}` : ''
  return request(`/api/study1/task-definitions/${encodeURIComponent(taskDefinitionId)}${query}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function validateTaskDefinition(taskDefinitionId, version = null) {
  const query = version ? `?version=${encodeURIComponent(version)}` : ''
  return request(`/api/study1/task-definitions/${encodeURIComponent(taskDefinitionId)}/validate${query}`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function fetchCurrentInstrument(sessionId) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/me/instrument`)
}

export function submitInstrumentResponse(
  sessionId,
  instrumentDefinitionId,
  instrumentVersion,
  orderedResponses,
) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/me/instrument`, {
    method: 'POST',
    body: JSON.stringify({
      instrument_definition_id: instrumentDefinitionId,
      instrument_version: instrumentVersion,
      ordered_responses: orderedResponses,
    }),
  })
}

export function submitIndividualDecision(
  sessionId,
  decisionKind,
  payload,
  instrumentVersion = '2.0',
) {
  return request(
    `/api/study1/sessions/${encodeURIComponent(sessionId)}/decisions/${formalSegment(decisionKind)}`,
    {
      method: 'POST',
      body: JSON.stringify({
        instrument_version: instrumentVersion,
        payload,
      }),
    },
  )
}

export function fetchSharedArtifact(sessionId, kind) {
  return request(
    `/api/study1/sessions/${encodeURIComponent(sessionId)}/shared-artifacts/${formalSegment(kind)}`,
  )
}

export function createSharedArtifactRevision(sessionId, kind, payload) {
  return request(
    `/api/study1/sessions/${encodeURIComponent(sessionId)}/shared-artifacts/${formalSegment(kind)}/revisions`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}

export function confirmSharedArtifactRevision(sessionId, kind, revisionId) {
  return request(
    `/api/study1/sessions/${encodeURIComponent(sessionId)}/shared-artifacts/${formalSegment(kind)}/revisions/${encodeURIComponent(revisionId)}/confirm`,
    {
      method: 'POST',
      body: JSON.stringify({}),
    },
  )
}

export function fetchMarkers(sessionId) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/markers`)
}

export function createMarker(sessionId, payload) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/markers`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchReplayPlans(sessionId) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/replay-plans`)
}

export function createReplayPlan(sessionId, payload) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/replay-plans`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function createSummaryAction(sessionId, payload) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/summary-actions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function submitSummaryQa(sessionId, summaryArtifactId, ratings) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/summary-qa`, {
    method: 'POST',
    body: JSON.stringify({
      summary_artifact_id: summaryArtifactId,
      ratings,
    }),
  })
}

export function reportQualityMetrics(sessionId, payload) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/quality-metrics`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchQualitySnapshot(sessionId) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/quality`)
}

export function createRetentionJob(payload) {
  return request('/api/study1/privacy/retention-jobs', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function executeRetentionJob(jobId, payload = {}) {
  return request(`/api/study1/privacy/retention-jobs/${encodeURIComponent(jobId)}/execute`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchStudy2Resource(sessionId, resource, { cursor = null, limit = null } = {}) {
  const query = new URLSearchParams()
  if (cursor != null) query.set('cursor', cursor)
  if (limit != null) query.set('limit', String(limit))
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return request(
    `/api/study2/v1/sessions/${encodeURIComponent(sessionId)}/${formalSegment(resource)}${suffix}`,
  )
}

export function fetchStudy1PrivacyScopes() {
  return request('/api/study1/privacy/scopes')
}

export function requestStudy1Withdrawal(sessionId, payload) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/privacy/withdrawal-requests`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function createStudy1Session(payload) {
  return request('/api/study1/sessions', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function uploadStudy1Materials(sessionId, role, files) {
  const form = new FormData()
  for (const file of files) form.append('files', file)
  return request(
    `/api/study1/sessions/${encodeURIComponent(sessionId)}/materials/${encodeURIComponent(role)}`,
    { method: 'POST', body: form },
  )
}

export function listStudy1Sessions() {
  return request('/api/study1/sessions')
}

export function fetchResearcherDashboard(sessionId) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/researcher`)
}

export function controlStudy1Session(sessionId, action, payload = {}) {
  return request(
    `/api/study1/sessions/${encodeURIComponent(sessionId)}/control/${encodeURIComponent(action)}`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}

export function addStudy1Incident(sessionId, payload) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/incidents`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function cloneStudy1Session(sessionId, sessionName) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/clone`, {
    method: 'POST',
    body: JSON.stringify({ session_name: sessionName }),
  })
}

export function addTranscriptCorrection(sessionId, payload) {
  return request(
    `/api/study1/sessions/${encodeURIComponent(sessionId)}/transcript-corrections`,
    { method: 'POST', body: JSON.stringify(payload) },
  )
}

export function issueStudy1MediaCommand(sessionId, command, payload = {}) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/media-commands`, {
    method: 'POST',
    body: JSON.stringify({ command, payload }),
  })
}

export function fetchMediaAccess(sessionId) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/media-access`, {
    method: 'POST',
    body: JSON.stringify({}),
  }).then(normalizeMediaAccess)
}

export function fetchMediaStatus(sessionId) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/media-status`)
    .then(normalizeResearcherMediaStatus)
}

export function reportMediaDevice(sessionId, payload) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/media-device`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function completeMockMedia(sessionId) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/mock-media/complete`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export async function exportStudy1Data(sessionId) {
  const response = await fetch(`/api/study1/sessions/${encodeURIComponent(sessionId)}/export`, {
    headers: { Authorization: `Bearer ${getStudy1Token()}` },
  })
  if (!response.ok) {
    let data = null
    try { data = await response.json() } catch {}
    throw new Error(data?.message || data?.error || `Export failed (${response.status})`)
  }
  return response.blob()
}

export function transitionPhase(sessionId, targetPhase, { override = false, reason = null } = {}) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/transition`, {
    method: 'POST',
    body: JSON.stringify({
      target_phase: targetPhase,
      override,
      reason,
    }),
  })
}

export function fetchReview(sessionId) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/review`)
}

export function logReviewUiEvent(sessionId, eventType, payload = {}) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/ui-events`, {
    method: 'POST',
    body: JSON.stringify({
      event_type: eventType,
      payload,
    }),
  })
}

export function sendReviewEventBatch(sessionId, payload) {
  return request(`/api/study1/sessions/${encodeURIComponent(sessionId)}/review-events/batch`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export { request as study1Request }
