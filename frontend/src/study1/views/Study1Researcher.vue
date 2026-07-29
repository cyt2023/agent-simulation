<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import PhaseHeader from '../components/PhaseHeader.vue'
import Study1FilePicker from '../components/Study1FilePicker.vue'
import {
  addStudy1Incident,
  controlStudy1Session,
  createStudy1Session,
  fetchResearcherDashboard,
  getStudy1Identity,
  listStudy1Sessions,
  researcherLogin,
  issueStudy1MediaCommand,
  completeMockMedia,
  exportStudy1Data,
  fetchMediaStatus,
  transitionPhase,
  uploadStudy1Materials,
} from '../services/study1Api.js'
import {
  buildSummaryRetryPayload,
  canEndMeeting,
  startCommandForPhase,
} from '../services/mediaControls.js'
import { displayMicrophoneLabel } from '../services/uiLabels.js'
import {
  joinStudy1Session,
  leaveStudy1Session,
  offStudy1Event,
  onStudy1Event,
} from '../services/study1Socket.js'

const authenticated = ref(getStudy1Identity()?.role === 'researcher')
const appOrigin = window.location.origin
const researcherKey = ref('')
const sessionName = ref('')
const minimumReviewSeconds = ref(0)
const materialText = ref({ principal: '', teammate_1: '', teammate_2: '' })
const materialFiles = ref({ principal: [], teammate_1: [], teammate_2: [] })
const sessionList = ref([])
const selectedSessionId = ref('')
const dashboard = ref(null)
const mediaStatus = ref(null)
const invites = ref([])
const busy = ref(false)
const error = ref('')
let refreshTimer = null

const nextPhase = computed(() => dashboard.value?.next_phase || null)

async function login() {
  busy.value = true
  error.value = ''
  try {
    await researcherLogin(researcherKey.value)
    authenticated.value = true
    researcherKey.value = ''
    await loadSessions()
  } catch (reason) {
    error.value = reason.message
  } finally {
    busy.value = false
  }
}

async function loadSessions() {
  const result = await listStudy1Sessions()
  sessionList.value = result.sessions
}

async function createSession() {
  busy.value = true
  error.value = ''
  try {
    const materialsByRole = Object.fromEntries(
      Object.entries(materialText.value).map(([role, content]) => [
        role,
        content.trim() ? [{ title: `${role.replaceAll('_', ' ')} material`, content: content.trim() }] : [],
      ]),
    )
    const result = await createStudy1Session({
      session_name: sessionName.value,
      minimum_review_seconds: Number(minimumReviewSeconds.value) || 0,
      materials_by_role: materialsByRole,
    })
    invites.value = result.invites
    selectedSessionId.value = result.session.session_id
    for (const role of ['principal', 'teammate_1', 'teammate_2']) {
      if (materialFiles.value[role].length) {
        await uploadStudy1Materials(
          selectedSessionId.value,
          role,
          materialFiles.value[role],
        )
      }
    }
    await loadSessions()
    await selectSession()
  } catch (reason) {
    error.value = reason.message
  } finally {
    busy.value = false
  }
}

async function selectSession() {
  if (!selectedSessionId.value) return
  leaveStudy1Session()
  await refreshDashboard()
  joinStudy1Session(selectedSessionId.value, refreshDashboard)
  window.clearInterval(refreshTimer)
  refreshTimer = window.setInterval(refreshDashboard, 5000)
}

async function refreshDashboard() {
  if (!selectedSessionId.value) return
  try {
    const [dashboardResult, mediaResult] = await Promise.all([
      fetchResearcherDashboard(selectedSessionId.value),
      fetchMediaStatus(selectedSessionId.value).catch(reason => ({
        service_status: 'unavailable',
        error: reason.message,
      })),
    ])
    dashboard.value = dashboardResult
    mediaStatus.value = mediaResult
  } catch (reason) {
    error.value = reason.message
  }
}

async function control(action, payload = {}) {
  busy.value = true
  error.value = ''
  try {
    await controlStudy1Session(selectedSessionId.value, action, payload)
    await refreshDashboard()
  } catch (reason) {
    error.value = reason.message
  } finally {
    busy.value = false
  }
}

async function advance(force = false) {
  if (!nextPhase.value) return
  let reason = null
  if (force) {
    reason = window.prompt('Reason for force advance (required):')?.trim()
    if (!reason) return
  }
  busy.value = true
  try {
    await transitionPhase(selectedSessionId.value, nextPhase.value, {
      override: force,
      reason,
    })
    await refreshDashboard()
  } catch (failure) {
    error.value = failure.message
  } finally {
    busy.value = false
  }
}

function extendPhase() {
  const seconds = Number(window.prompt('Extension in seconds:', '300'))
  if (seconds > 0) control('extend', { seconds })
}

async function addIncident() {
  const description = window.prompt('Incident description:')?.trim()
  if (!description) return
  try {
    await addStudy1Incident(selectedSessionId.value, {
      category: 'researcher_note',
      severity: 'warning',
      description,
    })
    await refreshDashboard()
  } catch (reason) {
    error.value = reason.message
  }
}

async function startMedia() {
  const command = startCommandForPhase(dashboard.value?.phase)
  if (!command) return
  await runMediaCommand(command)
}

async function runMediaCommand(command, payload = {}) {
  busy.value = true
  error.value = ''
  try {
    await issueStudy1MediaCommand(selectedSessionId.value, command, payload)
    await refreshDashboard()
  } catch (reason) {
    error.value = reason.message
  } finally {
    busy.value = false
  }
}

function endMeeting() {
  runMediaCommand('END_CURRENT_MEETING')
}

function regenerateSummary() {
  const reason = window.prompt('Reason for summary regeneration (required):')
  if (reason == null) return
  try {
    runMediaCommand(
      'REGENERATE_SUMMARY',
      buildSummaryRetryPayload(reason, mediaStatus.value),
    )
  } catch (failure) {
    error.value = failure.message
  }
}

async function confirmMockComplete() {
  try {
    await completeMockMedia(selectedSessionId.value)
    await refreshDashboard()
  } catch (reason) {
    error.value = reason.message
  }
}

async function exportData() {
  try {
    const blob = await exportStudy1Data(selectedSessionId.value)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `study1-${selectedSessionId.value}.zip`
    link.click()
    URL.revokeObjectURL(url)
  } catch (reason) {
    error.value = reason.message
  }
}

function handleStudyEvent(event) {
  if (event?.session_id === selectedSessionId.value) refreshDashboard()
}

onMounted(() => {
  for (const event of [
    'study1_phase_updated',
    'study1_readiness_updated',
    'study1_participant_status_updated',
    'study1_artifact_ready',
    'study1_incident_created',
    'study1_session_terminated',
  ]) onStudy1Event(event, handleStudyEvent)
  if (authenticated.value) loadSessions().catch(reason => { error.value = reason.message })
})

onUnmounted(() => {
  window.clearInterval(refreshTimer)
  leaveStudy1Session()
  for (const event of [
    'study1_phase_updated',
    'study1_readiness_updated',
    'study1_participant_status_updated',
    'study1_artifact_ready',
    'study1_incident_created',
    'study1_session_terminated',
  ]) offStudy1Event(event, handleStudyEvent)
})
</script>

<template>
  <main class="researcher-shell">
    <h1 v-if="!dashboard">Study 1 researcher console</h1>
    <p v-if="error" class="error">{{ error }}</p>

    <section v-if="!authenticated" class="panel login login-centered">
      <h2>Researcher sign in</h2>
      <label>Researcher key<input v-model="researcherKey" type="password" @keyup.enter="login" /></label>
      <button :disabled="busy || !researcherKey" @click="login">Sign in</button>
    </section>

    <template v-else>
      <section class="panel create">
        <h2>Create Study 1 session</h2>
        <div class="grid">
          <label>Session label<input v-model="sessionName" /></label>
          <label>Minimum review seconds<input v-model.number="minimumReviewSeconds" type="number" min="0" /></label>
        </div>
        <label v-for="role in ['principal', 'teammate_1', 'teammate_2']" :key="role">
          {{ role.replaceAll('_', ' ') }} private material
          <textarea v-model="materialText[role]" rows="3" />
          <Study1FilePicker
            :input-id="`study1-material-${role}`"
            @files-change="materialFiles[role] = $event"
          />
        </label>
        <button :disabled="busy || !sessionName.trim()" @click="createSession">Create session and invitations</button>
      </section>

      <section v-if="invites.length" class="panel invites">
        <h2>One-time invitation links</h2>
        <p>These raw tokens are shown once and are not stored in plaintext.</p>
        <div v-for="invite in invites" :key="invite.invite_id" class="invite">
          <strong>{{ invite.role }}</strong>
          <code>{{ `${appOrigin}${invite.join_path}` }}</code>
        </div>
      </section>

      <section class="panel">
        <label>
          Load session
          <select v-model="selectedSessionId" @change="selectSession">
            <option value="">Select…</option>
            <option v-for="item in sessionList" :key="item.session_id" :value="item.session_id">
              {{ item.session_name }} — {{ item.phase }}
            </option>
          </select>
        </label>
      </section>

      <template v-if="dashboard">
        <PhaseHeader
          :phase="dashboard.phase"
          :status="dashboard.status"
          :ready="dashboard.ready_to_advance"
        />
        <section class="metrics">
          <div><span>Phase started</span><strong>{{ dashboard.phase_started_at }}</strong></div>
          <div><span>Media</span><strong>{{ dashboard.media_service_status }}</strong></div>
          <div><span>Summary / transcript</span><strong>{{ dashboard.artifacts.summary }} / {{ dashboard.artifacts.transcript }}</strong></div>
          <div><span>Incidents</span><strong>{{ dashboard.incident_count }}</strong></div>
        </section>
        <section class="panel">
          <h2>Participants</h2>
          <table>
            <thead><tr><th>Role</th><th>Online</th><th>Completed actions</th></tr></thead>
            <tbody>
              <tr v-for="participant in dashboard.participants" :key="participant.participant_id">
                <td>{{ participant.role }}</td>
                <td>{{ participant.online ? 'online' : 'offline' }}</td>
                <td>{{ participant.completed_actions.join(', ') || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <p><strong>Not submitted:</strong> {{ dashboard.not_submitted.join(', ') || 'none' }}</p>
        </section>
        <section class="panel media-operations">
          <div class="panel-heading">
            <div>
              <h2>Meeting and Proxy service</h2>
              <p>{{ mediaStatus?.service_status || 'checking' }}</p>
            </div>
            <span class="service-state" :data-state="mediaStatus?.service_status">
              {{ mediaStatus?.runtime_state || 'IDLE' }}
            </span>
          </div>
          <dl class="media-grid">
            <div><dt>Room</dt><dd>{{ mediaStatus?.room_kind || 'none' }}<small>{{ mediaStatus?.room_name || '—' }}</small></dd></div>
            <div><dt>ASR</dt><dd>{{ mediaStatus?.asr?.status || '—' }}<small>{{ mediaStatus?.asr?.provider || '—' }}</small></dd></div>
            <div><dt>Proxy</dt><dd>{{ mediaStatus?.proxy?.active ? 'active' : 'inactive' }}<small>{{ mediaStatus?.proxy?.prompt_version || '—' }}</small></dd></div>
            <div><dt>Recording</dt><dd>{{ mediaStatus?.recording?.status || '—' }}<small>{{ mediaStatus?.pending_callback_count || 0 }} callbacks pending</small></dd></div>
          </dl>
          <table v-if="mediaStatus?.connections?.length">
            <thead><tr><th>Media participant</th><th>Role</th><th>Connection</th><th>Device</th></tr></thead>
            <tbody>
              <tr v-for="(connection, index) in mediaStatus.connections" :key="connection.participant_id">
                <td>{{ connection.participant_id }}</td>
                <td>{{ connection.role }}</td>
                <td>{{ connection.state }}</td>
                <td>{{ displayMicrophoneLabel(connection.device?.label, index) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="mediaStatus?.error" class="error">{{ mediaStatus.error }}</p>
        </section>
        <section class="controls" aria-label="Session controls">
          <div class="primary-controls">
            <button
              class="control-button control-button--major"
              :disabled="busy || dashboard.status !== 'waiting'"
              @click="control('start')"
            >
              Start Session
            </button>
            <button
              class="control-button control-button--major control-button--advance"
              :disabled="busy || !nextPhase || !dashboard.ready_to_advance"
              @click="advance(false)"
            >
              Advance Phase
            </button>
            <button
              v-if="['PROXY_MEETING','HANDOFF','SYNC_MEETING'].includes(dashboard.phase)"
              class="control-button control-button--major control-button--media"
              :disabled="busy"
              @click="startMedia"
            >
              {{ mediaStatus?.mode === 'mock' ? 'Issue Mock Media Command' : 'Start Media Operation' }}
            </button>
            <button
              v-if="['PROXY_MEETING','HANDOFF','SYNC_MEETING'].includes(dashboard.phase)"
              v-show="mediaStatus?.mode === 'mock'"
              class="control-button control-button--major control-button--media"
              :disabled="busy || mediaStatus?.mode !== 'mock'"
              @click="confirmMockComplete"
            >
              Confirm Mock Complete
            </button>
            <button
              v-if="canEndMeeting(dashboard.phase) && mediaStatus?.mode !== 'mock'"
              class="control-button control-button--major control-button--media"
              :disabled="busy"
              @click="endMeeting"
            >
              End Current Meeting
            </button>
          </div>

          <div class="supporting-controls">
            <div class="secondary-controls">
              <button :disabled="busy || dashboard.status !== 'running'" @click="control('pause')">Pause</button>
              <button :disabled="busy || dashboard.status !== 'paused'" @click="control('resume')">Resume</button>
              <button :disabled="busy" @click="extendPhase">Extend Phase</button>
              <button :disabled="busy" @click="addIncident">Add Incident</button>
              <button
                v-if="dashboard.phase === 'REVIEW' && mediaStatus?.mode !== 'mock'"
                :disabled="busy || !mediaStatus?.summary_version"
                @click="regenerateSummary"
              >
                Regenerate Summary
              </button>
              <button :disabled="busy" @click="exportData">Export Data</button>
            </div>
            <div class="safety-controls">
              <button
                class="danger"
                :disabled="busy || ['terminated','completed'].includes(dashboard.status)"
                @click="control('terminate', { reason: 'researcher action' })"
              >
                Terminate
              </button>
              <button class="danger" :disabled="busy || !nextPhase" @click="advance(true)">Force Advance</button>
            </div>
          </div>
        </section>
      </template>
    </template>
  </main>
</template>

<style scoped>
.researcher-shell { width:min(1080px, calc(100% - 2rem)); margin:2rem auto; color:#263746; font-family:Inter,ui-sans-serif,system-ui,sans-serif; }
.panel { background:#f9fbfc; border:1px solid #dce3e9; border-radius:12px; padding:1.25rem; margin:1.25rem 0; }
.login { max-width:460px; }
.login-centered { box-sizing:border-box; width:min(460px,100%); margin:1.25rem auto; }
.grid,.metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:1rem; }
label { display:grid; gap:.4rem; margin:.8rem 0; font-weight:650; }
input,textarea,select { padding:.65rem; border:1px solid #bac6d0; border-radius:7px; font:inherit; }
button { border:0; border-radius:7px; padding:.65rem .9rem; background:#265f8c; color:white; font-weight:700; cursor:pointer; transition:background-color .15s ease,box-shadow .15s ease,transform .15s ease; }
button:not(:disabled):hover { background:#1f5278; }
button:focus-visible { outline:3px solid rgba(38,95,140,.28); outline-offset:2px; }
button:disabled { opacity:.42; cursor:not-allowed; box-shadow:none; }
.danger { border:1px solid #c98585; background:#fff7f7; color:#8d2f2f; }
.danger:not(:disabled):hover { background:#fbe8e8; color:#792424; }
.error { background:#fff0f0; color:#922; padding:.75rem; border-radius:7px; }
.invite { display:grid; grid-template-columns:120px 1fr; gap:1rem; padding:.5rem 0; }
code { overflow-wrap:anywhere; }
.metrics { margin:1.25rem 0; }
.metrics div { display:grid; gap:.35rem; background:#edf3f7; border-radius:9px; padding:1rem; }
.metrics span { color:#667786; font-size:.78rem; text-transform:uppercase; }
table { width:100%; border-collapse:collapse; }
th,td { text-align:left; border-bottom:1px solid #dde4ea; padding:.65rem; }
.controls { display:grid; gap:.85rem; margin:1.25rem 0 3rem; padding:1rem; border:1px solid #dce3e9; border-radius:12px; background:#f9fbfc; }
.primary-controls,.secondary-controls,.safety-controls { display:flex; flex-wrap:wrap; gap:.65rem; }
.primary-controls { align-items:stretch; }
.control-button--major { min-height:3.25rem; padding:.85rem 1.25rem; font-size:1.02rem; box-shadow:0 5px 12px rgba(38,95,140,.16); }
.control-button--advance { background:#176b58; }
.control-button--advance:not(:disabled):hover { background:#125746; }
.control-button--media { background:#5a4a91; }
.control-button--media:not(:disabled):hover { background:#493b78; }
.supporting-controls { display:flex; align-items:center; justify-content:space-between; gap:.85rem; padding-top:.85rem; border-top:1px solid #dce3e9; }
.secondary-controls button,.safety-controls button { padding:.48rem .7rem; font-size:.86rem; font-weight:650; }
.panel-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; }
.panel-heading h2,.panel-heading p { margin:0; }
.panel-heading p { margin-top:.25rem; color:#667786; text-transform:capitalize; }
.service-state { padding:.35rem .55rem; border:1px solid #c6d0d8; border-radius:6px; color:#536471; font-size:.78rem; }
.service-state[data-state="ok"] { border-color:#70a883; background:#edf8f1; color:#17633c; }
.media-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1rem; margin:1.25rem 0; }
.media-grid div { min-width:0; border-left:3px solid #cad5dc; padding-left:.75rem; }
.media-grid dt { color:#667786; font-size:.75rem; font-weight:700; text-transform:uppercase; }
.media-grid dd { margin:.25rem 0 0; font-weight:700; overflow-wrap:anywhere; }
.media-grid small { display:block; margin-top:.2rem; color:#70808c; font-weight:400; }
@media (max-width:720px) {
  .media-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .primary-controls { display:grid; grid-template-columns:1fr; }
  .control-button--major { width:100%; }
  .supporting-controls { align-items:flex-start; flex-direction:column; }
}
</style>
