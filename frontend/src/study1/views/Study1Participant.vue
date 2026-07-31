<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PhaseHeader from '../components/PhaseHeader.vue'
import MaterialPhase from '../components/MaterialPhase.vue'
import VotePhase from '../components/VotePhase.vue'
import ProxyConfigPhase from '../components/ProxyConfigPhase.vue'
import WaitingRoom from '../components/WaitingRoom.vue'
import ReviewPhase from '../components/ReviewPhase.vue'
import SurveyPhase from '../components/SurveyPhase.vue'
import CompletionPhase from '../components/CompletionPhase.vue'
import Study1MeetingWorkspace from '../components/Study1MeetingWorkspace.vue'
import Study1DeviceCheck from '../components/Study1DeviceCheck.vue'
import ConsentPhase from '../components/ConsentPhase.vue'
import WithdrawalPhase from '../components/WithdrawalPhase.vue'
import { useStableAudioSession } from '../composables/useStableAudioSession.js'
import {
  clearStudy1Auth,
  createSubmission,
  exchangeInvite,
  fetchMe,
  fetchMyMaterials,
  getStudy1Identity,
  logReviewUiEvent,
  requestStudy1Withdrawal,
} from '../services/study1Api.js'
import {
  joinStudy1Session,
  leaveStudy1Session,
  offStudy1Event,
  onStudy1Event,
} from '../services/study1Socket.js'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const session = ref(null)
const identity = ref(getStudy1Identity())
const materials = ref([])
let errorTimer = null
let noticeTimer = null

const phase = computed(() => session.value?.phase || 'SETUP')
const role = computed(() => identity.value?.role || '')
const isParticipant = computed(() => ['principal', 'teammate_1', 'teammate_2'].includes(role.value))
const completedActions = computed(() => new Set(session.value?.my_completed_actions || []))
const hasCompleted = type => completedActions.value.has(`${type}:${role.value}`)

async function reportRtcTelemetry(sample) {
  const sessionId = identity.value?.session_id
  if (!sessionId) return
  try {
    await logReviewUiEvent(sessionId, 'rtc_metric_sample', sample)
  } catch {
    // Telemetry must never interrupt the participant's audio controls.
  }
}

const audioSession = useStableAudioSession({ onTelemetrySample: reportRtcTelemetry })
const teammateBridgePhases = new Set([
  'PROXY_MEETING',
  'TENTATIVE_DECISION',
  'DELEGATION_EXPECTATION',
  'REVIEW',
  'COMPREHENSION_MEASUREMENT',
  'HANDOFF',
  'SYNC_MEETING',
])
const meetingWorkspaceVisible = computed(() => {
  if (['HANDOFF', 'SYNC_MEETING'].includes(phase.value)) return true
  return ['teammate_1', 'teammate_2'].includes(role.value)
    && teammateBridgePhases.has(phase.value)
})
const workspaceTaskTitle = computed(() => ({
  PROXY_MEETING: 'Discuss the assigned task',
  TENTATIVE_DECISION: 'Record the tentative decision',
  DELEGATION_EXPECTATION: 'Wait for P to record expectations',
  REVIEW: 'Wait while P reviews the meeting record',
  COMPREHENSION_MEASUREMENT: 'Wait while P completes the measurement',
  HANDOFF: 'Prepare for P to rejoin',
  SYNC_MEETING: 'Synchronize as a three-person team',
}[phase.value] || 'Current study step'))
const workspaceTaskDescription = computed(() => ({
  PROXY_MEETING: 'Use the audio controls below the participant seats.',
  TENTATIVE_DECISION: 'Your audio connection remains available while you submit this form.',
  HANDOFF: 'Stay connected while the AI Proxy leaves and P joins.',
  SYNC_MEETING: 'Continue the task with P, T1, and T2.',
}[phase.value] || 'Remain on this page until the researcher advances the stage.'))

function clearError() {
  window.clearTimeout(errorTimer)
  errorTimer = null
  error.value = ''
}

function clearNotice() {
  window.clearTimeout(noticeTimer)
  noticeTimer = null
  notice.value = ''
}

function showTransientError(message) {
  clearError()
  error.value = message
  errorTimer = window.setTimeout(clearError, 6000)
}

function showTransientNotice(message) {
  clearNotice()
  notice.value = message
  noticeTimer = window.setTimeout(clearNotice, 4500)
}

async function refresh() {
  if (!identity.value?.session_id) return
  const result = await fetchMe(identity.value.session_id)
  identity.value = result.identity
  session.value = result.session
  if (
    phase.value === 'MATERIAL_READING'
    || (phase.value === 'PROXY_CONFIGURATION' && role.value === 'principal')
  ) {
    materials.value = (await fetchMyMaterials(identity.value.session_id)).materials
  }
}

async function bootstrap() {
  loading.value = true
  error.value = ''
  try {
    if (route.params.token) {
      const exchanged = await exchangeInvite(route.params.token)
      identity.value = exchanged.identity
      await router.replace('/study1/participant')
    }
    identity.value = getStudy1Identity()
    if (!isParticipant.value || !identity.value?.session_id) {
      throw new Error('A valid one-time Study 1 invitation is required.')
    }
    await refresh()
    joinStudy1Session(identity.value.session_id, () => refresh().catch(showError))
  } catch (reason) {
    showError(reason)
  } finally {
    loading.value = false
  }
}

function showError(reason) {
  let message = ''
  if (reason?.data?.error === 'ACTION_NOT_ALLOWED_IN_PHASE') {
    message = `This action requires ${reason.data.required_phase}; the server is currently in ${reason.data.current_phase}.`
  } else {
    message = reason?.message || 'Unable to load Study 1.'
  }
  if (session.value) showTransientError(message)
  else error.value = message
}

async function submit(type, payload) {
  busy.value = true
  clearError()
  clearNotice()
  try {
    await createSubmission(identity.value.session_id, type, payload, '2.0')
    showTransientNotice('Saved and locked. Please wait for the researcher.')
    await refresh()
  } catch (reason) {
    showError(reason)
  } finally {
    busy.value = false
  }
}

async function submitWithdrawal(payload) {
  busy.value = true
  clearError()
  clearNotice()
  try {
    await requestStudy1Withdrawal(identity.value.session_id, payload)
    showTransientNotice('Withdrawal request submitted for privacy review.')
  } catch (reason) {
    showError(reason)
  } finally {
    busy.value = false
  }
}

function onPhaseEvent(event) {
  if (event?.session_id === identity.value?.session_id) refresh().catch(showError)
}

watch(phase, (currentPhase, previousPhase) => {
  if (currentPhase !== previousPhase) {
    clearError()
    clearNotice()
  }
})
watch(
  [phase, () => session.value?.phase_version, role],
  ([currentPhase, phaseVersion, currentRole]) => {
    audioSession
      .syncAuthoritativePhase(currentPhase, Number(phaseVersion) || 0, currentRole)
      .catch(showError)
  },
)

onMounted(() => {
  onStudy1Event('study1_phase_updated', onPhaseEvent)
  onStudy1Event('study1_readiness_updated', onPhaseEvent)
  onStudy1Event('study1_session_terminated', onPhaseEvent)
  bootstrap()
})

onUnmounted(() => {
  window.clearTimeout(errorTimer)
  window.clearTimeout(noticeTimer)
  offStudy1Event('study1_phase_updated', onPhaseEvent)
  offStudy1Event('study1_readiness_updated', onPhaseEvent)
  offStudy1Event('study1_session_terminated', onPhaseEvent)
  leaveStudy1Session()
  audioSession.dispose()
})
</script>

<template>
  <main class="study-shell">
    <div v-if="loading" class="card">Loading the authoritative study state...</div>
    <div v-else-if="!session" class="card error-card">
      <h1>Study 1 access unavailable</h1>
      <p>{{ error }}</p>
      <button @click="clearStudy1Auth(); router.replace('/')">Return</button>
    </div>
    <template v-else>
      <PhaseHeader
        :phase="session.phase"
        :status="session.status"
        :ready="session.ready_to_advance"
        :remaining-seconds="session.remaining_seconds"
        :session-id="identity.session_id"
      />
      <p class="role-label">Signed in as {{ role.replaceAll('_', ' ') }}</p>
      <p v-if="error" class="message error">{{ error }}</p>
      <p v-if="notice" class="message success">{{ notice }}</p>
      <Study1MeetingWorkspace
        v-if="meetingWorkspaceVisible"
        :session-id="identity.session_id"
        :phase="phase"
        :phase-version="session.phase_version"
        :role="role"
        :audio-session="audioSession"
        :task-title="workspaceTaskTitle"
        :task-description="workspaceTaskDescription"
        :remaining-seconds="session.remaining_seconds"
        @error="showTransientError($event)"
      >
        <VotePhase
          v-if="phase === 'TENTATIVE_DECISION'"
          title="Tentative decision"
          variant="tentative"
          :busy="busy"
          @submit="submit('tentative_decision', $event)"
        />
        <WaitingRoom
          v-else-if="['DELEGATION_EXPECTATION', 'REVIEW', 'COMPREHENSION_MEASUREMENT'].includes(phase)"
          message="Your audio connection is being kept ready. Wait for the researcher to continue."
        />
        <p v-else class="meeting-guidance">
          {{ phase === 'PROXY_MEETING'
            ? 'Discuss the task with the participants shown in the meeting.'
            : 'Use the shared audio room for this stage.' }}
        </p>
      </Study1MeetingWorkspace>
      <div v-else class="card">
        <section v-if="phase === 'SETUP'">
          <ConsentPhase
            :role="role"
            :consent-version="session.consent_version"
            :busy="busy"
            :locked="hasCompleted('consent')"
            @submit="submit('consent', $event)"
          />
          <Study1DeviceCheck :session-id="identity.session_id" />
          <WaitingRoom message="The researcher has not started the session." />
        </section>
        <MaterialPhase
          v-else-if="phase === 'MATERIAL_READING'"
          :materials="materials"
          :busy="busy"
          @acknowledge="submit('material_ack', { acknowledged: true })"
        />
        <VotePhase
          v-else-if="phase === 'PRE_VOTE'"
          title="Initial judgment"
          variant="pre"
          :busy="busy"
          :locked="hasCompleted(role === 'principal' ? 'proxy_config' : 'proxy_ready')"
          @submit="submit('pre_vote', $event)"
        />
        <ProxyConfigPhase
          v-else-if="phase === 'PROXY_CONFIGURATION'"
          :role="role"
          :materials="materials"
          :busy="busy"
          @submit="submit(role === 'principal' ? 'proxy_config' : 'proxy_ready', $event)"
        />
        <WaitingRoom
          v-else-if="phase === 'PROXY_MEETING'"
          :message="session.waiting_room?.message || 'The delegated discussion is in progress.'"
          :remaining-seconds="session.waiting_room?.remaining_seconds"
          :connection-status="session.waiting_room?.connection_status || 'connected'"
        />
        <WaitingRoom v-else-if="phase === 'TENTATIVE_DECISION'" />
        <SurveyPhase
          v-else-if="phase === 'DELEGATION_EXPECTATION' && role === 'principal'"
          title="Delegation expectation"
          instrument="delegation_expectation"
          :busy="busy"
          @submit="submit('delegation_expectation', $event)"
        />
        <WaitingRoom v-else-if="phase === 'DELEGATION_EXPECTATION'" />
        <ReviewPhase
          v-else-if="phase === 'REVIEW' && role === 'principal'"
          :session-id="identity.session_id"
        />
        <WaitingRoom v-else-if="phase === 'REVIEW'" />
        <SurveyPhase
          v-else-if="phase === 'COMPREHENSION_MEASUREMENT' && role === 'principal'"
          title="Comprehension measurement"
          instrument="comprehension_measurement"
          :busy="busy"
          @submit="submit('comprehension_measurement', $event)"
        />
        <WaitingRoom v-else-if="phase === 'COMPREHENSION_MEASUREMENT'" />
        <VotePhase
          v-else-if="phase === 'FINAL_DECISION'"
          title="Final decision"
          variant="final"
          :busy="busy"
          @submit="submit('final_decision', $event)"
        />
        <SurveyPhase
          v-else-if="phase === 'FOLLOWUP_TASK'"
          title="Follow-up collaboration task"
          instrument="followup_task"
          :busy="busy"
          @submit="submit('followup_task', $event)"
        />
        <SurveyPhase
          v-else-if="phase === 'POST_SURVEY'"
          title="Final questionnaire"
          instrument="post_survey"
          :busy="busy"
          @submit="submit('post_survey', $event)"
        />
        <section v-else-if="phase === 'COMPLETED'">
          <CompletionPhase />
          <WithdrawalPhase
            :session-id="identity.session_id"
            :role="role"
            :busy="busy"
            @submit="submitWithdrawal"
          />
        </section>
      </div>
    </template>
  </main>
</template>

<style scoped>
:global(body) { background:#eef1f2; }
.study-shell { width:min(1180px, calc(100% - 2rem)); min-height:100vh; margin:1.25rem auto 2rem; color:#263746; font-family:Inter, ui-sans-serif, system-ui, sans-serif; }
.card { background:#f9fbfc; border:1px solid #dce3e9; border-radius:8px; margin-top:1.25rem; padding:1.5rem; box-shadow:0 10px 28px rgba(39,58,74,.06); }
.role-label { color:#667482; font-size:.85rem; text-transform:capitalize; }
.meeting-guidance { margin:0; color:#5f6f79; line-height:1.55; }
.message { padding:.75rem 1rem; border-radius:8px; animation:message-in .18s ease-out; }
.error { background:#fff0f0; color:#9b2828; }
.success { background:#e9f7ef; color:#17633c; }
.error-card { text-align:center; margin-top:5rem; }
button { border:0; border-radius:8px; background:#245f8e; color:white; padding:.7rem 1rem; font:inherit; font-weight:700; cursor:pointer; }
button:disabled { opacity:.5; cursor:not-allowed; }
@keyframes message-in { from { opacity:0; transform:translateY(-4px); } to { opacity:1; transform:translateY(0); } }
</style>
