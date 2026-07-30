<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RefreshCw } from '@lucide/vue'

import { useStableAudioSession } from '../composables/useStableAudioSession.js'
import { displayMicrophoneLabel } from '../services/uiLabels.js'
import MeetingControls from './MeetingControls.vue'

const props = defineProps({
  sessionId: { type: String, required: true },
  phase: { type: String, required: true },
  phaseVersion: { type: Number, required: true },
  role: { type: String, required: true },
  audioSession: { type: Object, default: null },
  showRoster: { type: Boolean, default: true },
  embedded: Boolean,
})
const emit = defineEmits(['error'])

const ownedSession = props.audioSession ? null : useStableAudioSession()
const session = props.audioSession || ownedSession
const devices = ref([])
const selectedDeviceId = ref('')
const deviceState = ref('checking')
const localError = ref('')
const audioHost = ref(null)

function valueOf(source, fallback) {
  if (source && typeof source === 'object' && 'value' in source) return source.value
  return source ?? fallback
}

const connectionState = computed(() => valueOf(session.connectionState, 'disconnected'))
const reconnectSeconds = computed(() => Number(valueOf(session.reconnectSecondsRemaining, 0)))
const muted = computed(() => Boolean(valueOf(session.muted, false)))
const sessionError = computed(() => String(valueOf(session.error, '')))
const remoteIdentities = computed(() => valueOf(session.remoteIdentities, new Set()))
const activeIdentities = computed(() => valueOf(session.activeIdentities, new Set()))
const outputDevices = computed(() => valueOf(session.outputDevices, []))
const selectedOutputId = computed(() => String(valueOf(session.selectedOutputId, '')))
const outputSupported = computed(() => Boolean(valueOf(session.outputSupported, false)))
const outputNotice = computed(() => String(valueOf(session.outputNotice, '')))
const canJoin = computed(() => (
  deviceState.value === 'ready'
  && Boolean(selectedDeviceId.value)
  && ['disconnected', 'reconnect_failed'].includes(connectionState.value)
))
const expectedRoles = computed(() => (
  props.phase === 'PROXY_MEETING'
    ? ['teammate_1', 'teammate_2', 'proxy']
    : ['principal', 'teammate_1', 'teammate_2']
))

function readableRole(role) {
  return {
    principal: 'P',
    teammate_1: 'T1',
    teammate_2: 'T2',
    proxy: 'X',
  }[role] || role
}

function reportError(reason, fallback) {
  const message = reason?.message || fallback
  localError.value = message
  emit('error', message)
}

async function checkMicrophone() {
  deviceState.value = 'checking'
  localError.value = ''
  try {
    const permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    permissionStream.getTracks().forEach(track => track.stop())
    const availableDevices = await navigator.mediaDevices.enumerateDevices()
    devices.value = availableDevices.filter(device => device.kind === 'audioinput')
    session.configureOutputDevices?.(availableDevices)
    if (!devices.value.some(device => device.deviceId === selectedDeviceId.value)) {
      selectedDeviceId.value = devices.value[0]?.deviceId || ''
    }
    deviceState.value = selectedDeviceId.value ? 'ready' : 'missing'
  } catch (reason) {
    deviceState.value = 'denied'
    reportError(reason, 'Microphone access is required for this meeting.')
  }
}

async function joinAudio() {
  if (!canJoin.value) return
  const connected = await session.connect({
    sessionId: props.sessionId,
    phase: props.phase,
    phaseVersion: props.phaseVersion,
    role: props.role,
    deviceId: selectedDeviceId.value,
  })
  if (!connected && sessionError.value) emit('error', sessionError.value)
}

async function toggleMute() {
  const changed = await session.toggleMute()
  if (changed === false && sessionError.value) emit('error', sessionError.value)
}

async function leaveAudio() {
  await session.disconnect()
}

async function selectOutput(deviceId) {
  const changed = await session.setOutputDevice?.(deviceId)
  if (changed === false && valueOf(session.outputNotice, '')) {
    emit('error', valueOf(session.outputNotice, ''))
  }
}

watch(sessionError, message => {
  if (message) emit('error', message)
})

watch(
  () => [props.phase, props.phaseVersion],
  () => {
    // Standalone use has no participant shell to preserve the authoritative
    // room lifecycle, so invalidate any in-flight access request.
    if (ownedSession) ownedSession.disconnect()
  },
)

watch(audioHost, async element => {
  await nextTick()
  session.setAudioHost?.(element)
})

onMounted(checkMicrophone)
onUnmounted(() => {
  session.setAudioHost?.(null)
  if (ownedSession) ownedSession.dispose()
})
</script>

<template>
  <section class="voice-room" :class="{ embedded }" aria-label="Audio meeting connection">
    <div v-if="showRoster" class="participants" aria-label="Meeting participants">
      <div
        v-for="participantRole in expectedRoles"
        :key="participantRole"
        class="participant"
        :class="{ active: activeIdentities.has(participantRole) }"
        :data-role="participantRole"
      >
        <span class="avatar" aria-hidden="true">{{ readableRole(participantRole) }}</span>
        <div>
          <strong>{{ participantRole === 'proxy' ? 'X (Proxy)' : readableRole(participantRole) }}</strong>
          <span v-if="participantRole === 'proxy'">
            {{ remoteIdentities.has('proxy') ? 'Proxy is connected' : 'Proxy is joining the room' }}
          </span>
          <span v-else>
            {{ participantRole === role ? 'you' : (remoteIdentities.has(participantRole) ? 'connected' : 'waiting') }}
          </span>
        </div>
      </div>
    </div>

    <div class="device-row">
      <label for="study1-microphone">Microphone</label>
      <select
        id="study1-microphone"
        v-model="selectedDeviceId"
        :disabled="!['disconnected', 'reconnect_failed'].includes(connectionState)"
      >
        <option v-if="!devices.length" value="">No microphone available</option>
        <option v-for="(device, index) in devices" :key="device.deviceId" :value="device.deviceId">
          {{ displayMicrophoneLabel(device.label, index) }}
        </option>
      </select>
      <button
        class="check-button"
        type="button"
        title="Check microphone"
        :disabled="connectionState === 'connecting'"
        @click="checkMicrophone"
      >
        <RefreshCw :size="18" aria-hidden="true" />
        <span class="sr-only">Check microphone</span>
      </button>
    </div>

    <p v-if="deviceState === 'denied' || deviceState === 'missing'" class="room-error">
      {{ localError || 'No microphone was detected.' }}
    </p>
    <p v-else-if="localError || sessionError" class="room-error">{{ localError || sessionError }}</p>

    <MeetingControls
      :connection-state="connectionState"
      :reconnect-seconds="reconnectSeconds"
      :muted="muted"
      :can-join="canJoin"
      :busy="connectionState === 'connecting'"
      :output-devices="outputDevices"
      :selected-output-id="selectedOutputId"
      :output-supported="outputSupported"
      :output-notice="outputNotice"
      @join="joinAudio"
      @toggle-mute="toggleMute"
      @leave="leaveAudio"
      @select-output="selectOutput"
    />
    <p v-if="connectionState === 'connected'" data-test="microphone-status" class="microphone-status">
      {{ phase === 'HANDOFF' ? 'Stay connected while P joins and the AI Proxy leaves.' : `Microphone ${muted ? 'muted' : 'live'}` }}
    </p>
    <div ref="audioHost" hidden />
  </section>
</template>

<style scoped>
.voice-room { display:grid; background:#fff; }
.voice-room.embedded { background:#182126; color:#eef3f4; }
.participants { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.75rem; padding:1rem; }
.participant { min-width:0; display:flex; align-items:center; gap:.65rem; padding:.75rem; border:1px solid #dce3e9; border-radius:6px; background:#fff; }
.participant.active { border-color:#2f7c5d; box-shadow:inset 3px 0 #2f7c5d; }
.participant div { min-width:0; display:grid; }
.participant strong,.participant span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.participant div span { color:#6a7782; font-size:.76rem; }
.avatar { flex:0 0 36px; width:36px; height:36px; display:grid; place-items:center; border-radius:50%; background:#e8edf1; color:#31414e; font-size:.78rem; font-weight:800; }
.device-row { display:grid; grid-template-columns:auto minmax(0,1fr) 40px; align-items:center; gap:.75rem; padding:.8rem 1rem; border-top:1px solid #d8dfe4; }
select { min-width:0; width:100%; padding:.58rem; border:1px solid #bac6d0; border-radius:6px; background:#fff; color:#263746; font:inherit; }
.check-button { width:40px; height:40px; display:grid; place-items:center; border:1px solid #bdc8ce; border-radius:6px; background:#fff; color:#344853; cursor:pointer; }
.check-button:disabled { opacity:.45; cursor:not-allowed; }
.microphone-status { margin:0; padding:.55rem 1rem; border-top:1px solid #e2e7ea; color:#52616d; font-size:.78rem; text-align:center; }
.room-error { margin:0; padding:.65rem 1rem; border-top:1px solid #efd2d2; background:#fff0f0; color:#922; }
.embedded .device-row { border-color:#354148; background:#182126; color:#c7d2d6; }
.embedded select { border-color:#4a585e; background:#222d32; color:#edf3f4; }
.embedded .check-button { border-color:#4a585e; background:#222d32; color:#edf3f4; }
.embedded .microphone-status { border-color:#354148; background:#182126; color:#aebcc2; }
.embedded .room-error { border-color:#6b3f43; background:#321f22; color:#ffcccc; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
@media (max-width:620px) { .participants { grid-template-columns:1fr; } .device-row { grid-template-columns:1fr 40px; } .device-row label { grid-column:1/-1; } }
</style>
