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
import HandoffPhase from '../components/HandoffPhase.vue'
import CompletionPhase from '../components/CompletionPhase.vue'
import Study1VoiceRoom from '../components/Study1VoiceRoom.vue'
import Study1DeviceCheck from '../components/Study1DeviceCheck.vue'
import {
  clearStudy1Auth,
  createSubmission,
  exchangeInvite,
  fetchMe,
  fetchMyMaterials,
  getStudy1Identity,
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
    await createSubmission(identity.value.session_id, type, payload)
    showTransientNotice('Saved and locked. Please wait for the researcher.')
    await refresh()
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
})
</script>

<template>
  <main class="study-shell">
    <div v-if="loading" class="card">Loading the authoritative study state…</div>
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
      />
      <p class="role-label">Signed in as {{ role.replaceAll('_', ' ') }}</p>
      <p v-if="error" class="message error">{{ error }}</p>
      <p v-if="notice" class="message success">{{ notice }}</p>
      <div class="card">
        <section v-if="phase === 'SETUP'">
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
          :busy="busy"
          @submit="submit('pre_vote', $event)"
        />
        <ProxyConfigPhase
          v-else-if="phase === 'PROXY_CONFIGURATION'"
          :role="role"
          :materials="materials"
          :busy="busy"
          @submit="submit(role === 'principal' ? 'proxy_config' : 'proxy_ready', $event)"
        />
        <Study1VoiceRoom
          v-else-if="phase === 'PROXY_MEETING' && role !== 'principal'"
          :session-id="identity.session_id"
          :phase="phase"
          :phase-version="session.phase_version"
          :role="role"
          @error="showTransientError($event)"
        />
        <WaitingRoom
          v-else-if="phase === 'PROXY_MEETING'"
          :message="session.waiting_room?.message || 'The delegated discussion is in progress.'"
          :remaining-seconds="session.waiting_room?.remaining_seconds"
          :connection-status="session.waiting_room?.connection_status || 'connected'"
        />
        <VotePhase
          v-else-if="phase === 'TENTATIVE_DECISION' && role !== 'principal'"
          title="Tentative decision"
          :busy="busy"
          @submit="submit('tentative_decision', $event)"
        />
        <WaitingRoom v-else-if="phase === 'TENTATIVE_DECISION'" />
        <SurveyPhase
          v-else-if="phase === 'DELEGATION_EXPECTATION' && role === 'principal'"
          title="Delegation expectation"
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
          :busy="busy"
          @submit="submit('comprehension_measurement', $event)"
        />
        <WaitingRoom v-else-if="phase === 'COMPREHENSION_MEASUREMENT'" />
        <HandoffPhase v-else-if="phase === 'HANDOFF'" />
        <Study1VoiceRoom
          v-else-if="phase === 'SYNC_MEETING'"
          :session-id="identity.session_id"
          :phase="phase"
          :phase-version="session.phase_version"
          :role="role"
          @error="showTransientError($event)"
        />
        <VotePhase
          v-else-if="phase === 'FINAL_DECISION'"
          title="Final decision"
          :busy="busy"
          @submit="submit('final_decision', $event)"
        />
        <SurveyPhase
          v-else-if="phase === 'FOLLOWUP_TASK'"
          title="Follow-up collaboration task"
          :busy="busy"
          @submit="submit('followup_task', $event)"
        />
        <SurveyPhase
          v-else-if="phase === 'POST_SURVEY'"
          title="Final questionnaire"
          :busy="busy"
          @submit="submit('post_survey', $event)"
        />
        <CompletionPhase v-else-if="phase === 'COMPLETED'" />
      </div>
    </template>
  </main>
</template>

<style scoped>
.study-shell { width:min(840px, calc(100% - 2rem)); margin:2rem auto; color:#263746; font-family:Inter, ui-sans-serif, system-ui, sans-serif; }
.card { background:#f9fbfc; border:1px solid #dce3e9; border-radius:14px; margin-top:1.25rem; padding:1.5rem; box-shadow:0 10px 28px rgba(39,58,74,.06); }
.role-label { color:#667482; font-size:.85rem; text-transform:capitalize; }
.message { padding:.75rem 1rem; border-radius:8px; animation:message-in .18s ease-out; }
.error { background:#fff0f0; color:#9b2828; }
.success { background:#e9f7ef; color:#17633c; }
.error-card { text-align:center; margin-top:5rem; }
button { border:0; border-radius:8px; background:#245f8e; color:white; padding:.7rem 1rem; font:inherit; font-weight:700; cursor:pointer; }
button:disabled { opacity:.5; cursor:not-allowed; }
@keyframes message-in { from { opacity:0; transform:translateY(-4px); } to { opacity:1; transform:translateY(0); } }
</style>
