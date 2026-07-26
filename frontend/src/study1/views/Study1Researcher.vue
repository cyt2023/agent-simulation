<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import PhaseHeader from '../components/PhaseHeader.vue'
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
  transitionPhase,
  uploadStudy1Materials,
} from '../services/study1Api.js'
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
    dashboard.value = await fetchResearcherDashboard(selectedSessionId.value)
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

async function startMockMedia() {
  const commandByPhase = {
    PROXY_MEETING: 'START_PROXY_MEETING',
    HANDOFF: 'BEGIN_HANDOFF',
    SYNC_MEETING: 'START_SYNC_MEETING',
  }
  const command = commandByPhase[dashboard.value?.phase]
  if (!command) return
  try {
    await issueStudy1MediaCommand(selectedSessionId.value, command)
    await refreshDashboard()
  } catch (reason) {
    error.value = reason.message
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

    <section v-if="!authenticated" class="panel login">
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
          <input
            type="file"
            accept=".pdf,.txt,.md"
            multiple
            @change="materialFiles[role] = Array.from($event.target.files || [])"
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
        <section class="controls">
          <button :disabled="busy || dashboard.status !== 'waiting'" @click="control('start')">Start Session</button>
          <button :disabled="busy || !nextPhase || !dashboard.ready_to_advance" @click="advance(false)">Advance Phase</button>
          <button :disabled="busy || dashboard.status !== 'running'" @click="control('pause')">Pause</button>
          <button :disabled="busy || dashboard.status !== 'paused'" @click="control('resume')">Resume</button>
          <button :disabled="busy" @click="extendPhase">Extend Phase</button>
          <button :disabled="busy || ['terminated','completed'].includes(dashboard.status)" @click="control('terminate', { reason: 'researcher action' })">Terminate</button>
          <button class="danger" :disabled="busy || !nextPhase" @click="advance(true)">Force Advance</button>
          <button :disabled="busy" @click="addIncident">Add Incident</button>
          <button
            v-if="['PROXY_MEETING','HANDOFF','SYNC_MEETING'].includes(dashboard.phase)"
            :disabled="busy"
            @click="startMockMedia"
          >
            Issue Mock Media Command
          </button>
          <button
            v-if="['PROXY_MEETING','HANDOFF','SYNC_MEETING'].includes(dashboard.phase)"
            :disabled="busy"
            @click="confirmMockComplete"
          >
            Confirm Mock Complete
          </button>
          <button :disabled="busy" @click="exportData">Export Data</button>
        </section>
      </template>
    </template>
  </main>
</template>

<style scoped>
.researcher-shell { width:min(1080px, calc(100% - 2rem)); margin:2rem auto; color:#263746; font-family:Inter,ui-sans-serif,system-ui,sans-serif; }
.panel { background:#f9fbfc; border:1px solid #dce3e9; border-radius:12px; padding:1.25rem; margin:1.25rem 0; }
.login { max-width:460px; }
.grid,.metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:1rem; }
label { display:grid; gap:.4rem; margin:.8rem 0; font-weight:650; }
input,textarea,select { padding:.65rem; border:1px solid #bac6d0; border-radius:7px; font:inherit; }
button { border:0; border-radius:7px; padding:.65rem .9rem; background:#265f8c; color:white; font-weight:700; cursor:pointer; }
button:disabled { opacity:.45; cursor:not-allowed; }
.danger { background:#9c3434; }
.error { background:#fff0f0; color:#922; padding:.75rem; border-radius:7px; }
.invite { display:grid; grid-template-columns:120px 1fr; gap:1rem; padding:.5rem 0; }
code { overflow-wrap:anywhere; }
.metrics { margin:1.25rem 0; }
.metrics div { display:grid; gap:.35rem; background:#edf3f7; border-radius:9px; padding:1rem; }
.metrics span { color:#667786; font-size:.78rem; text-transform:uppercase; }
table { width:100%; border-collapse:collapse; }
th,td { text-align:left; border-bottom:1px solid #dde4ea; padding:.65rem; }
.controls { display:flex; flex-wrap:wrap; gap:.65rem; margin:1.25rem 0 3rem; }
</style>
