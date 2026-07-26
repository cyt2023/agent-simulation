<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Headphones, Mic, MicOff, PhoneOff, RefreshCw } from '@lucide/vue'
import { Room, RoomEvent } from 'livekit-client'

import { fetchMediaAccess } from '../services/study1Api.js'

const props = defineProps({
  sessionId: { type: String, required: true },
  phase: { type: String, required: true },
  phaseVersion: { type: Number, required: true },
  role: { type: String, required: true },
})

const emit = defineEmits(['error'])
const devices = ref([])
const selectedDeviceId = ref('')
const deviceState = ref('checking')
const connectionState = ref('disconnected')
const muted = ref(false)
const error = ref('')
const remoteIdentities = ref(new Set())
const activeIdentities = ref(new Set())
const audioHost = ref(null)
let room = null
let connectionGeneration = 0
let disposed = false

const expectedRoles = computed(() => (
  props.phase === 'PROXY_MEETING'
    ? ['teammate_1', 'teammate_2', 'proxy']
    : ['principal', 'teammate_1', 'teammate_2']
))
const canJoin = computed(() => (
  deviceState.value === 'ready'
  && Boolean(selectedDeviceId.value)
  && connectionState.value === 'disconnected'
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
  error.value = reason?.message || fallback
  emit('error', error.value)
}

async function checkMicrophone() {
  deviceState.value = 'checking'
  error.value = ''
  try {
    const permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    permissionStream.getTracks().forEach(track => track.stop())
    devices.value = (await navigator.mediaDevices.enumerateDevices())
      .filter(device => device.kind === 'audioinput')
    selectedDeviceId.value = devices.value[0]?.deviceId || ''
    deviceState.value = selectedDeviceId.value ? 'ready' : 'missing'
  } catch (reason) {
    deviceState.value = 'denied'
    reportError(reason, 'Microphone access is required for this meeting.')
  }
}

function syncParticipants() {
  if (!room) return
  remoteIdentities.value = new Set(
    [...room.remoteParticipants.values()].map(
      participant => participant.name || participant.identity,
    ),
  )
}

function attachTrack(track) {
  const element = track.attach()
  element.autoplay = true
  element.dataset.study1RemoteAudio = 'true'
  audioHost.value?.appendChild(element)
}

function detachTrack(track) {
  track.detach().forEach(element => element.remove())
}

async function joinAudio() {
  if (!canJoin.value) return
  const generation = ++connectionGeneration
  const requestedSession = props.sessionId
  const requestedPhase = props.phase
  const requestedVersion = props.phaseVersion
  let candidate = null
  connectionState.value = 'connecting'
  error.value = ''
  try {
    const access = await fetchMediaAccess(props.sessionId)
    if (access.available === false) throw new Error('Live media is not enabled for this session.')
    if (
      disposed
      || generation !== connectionGeneration
      || requestedSession !== props.sessionId
      || requestedPhase !== props.phase
      || requestedVersion !== props.phaseVersion
    ) return
    candidate = new Room({ adaptiveStream: true, dynacast: false })
    room = candidate
    candidate
      .on(RoomEvent.TrackSubscribed, attachTrack)
      .on(RoomEvent.TrackUnsubscribed, detachTrack)
      .on(RoomEvent.ActiveSpeakersChanged, speakers => {
        activeIdentities.value = new Set(
          speakers.map(participant => participant.name || participant.identity),
        )
      })
      .on(RoomEvent.ConnectionStateChanged, state => {
        connectionState.value = String(state).toLowerCase()
      })
      .on(RoomEvent.ParticipantConnected, syncParticipants)
      .on(RoomEvent.ParticipantDisconnected, syncParticipants)
    await candidate.connect(access.url, access.token)
    if (disposed || generation !== connectionGeneration || room !== candidate) {
      await candidate.disconnect()
      return
    }
    await candidate.localParticipant.setMicrophoneEnabled(
      true,
      { deviceId: selectedDeviceId.value },
    )
    muted.value = false
    connectionState.value = 'connected'
    syncParticipants()
  } catch (reason) {
    if (candidate) await candidate.disconnect()
    if (room === candidate) room = null
    if (generation === connectionGeneration && !disposed) {
      connectionState.value = 'disconnected'
      reportError(reason, 'Unable to join the audio meeting.')
    }
  }
}

async function toggleMute() {
  if (!room || connectionState.value !== 'connected') return
  muted.value = !muted.value
  await room.localParticipant.setMicrophoneEnabled(
    !muted.value,
    { deviceId: selectedDeviceId.value },
  )
}

async function disconnectRoom() {
  const generation = ++connectionGeneration
  const activeRoom = room
  room = null
  if (activeRoom) await activeRoom.disconnect()
  remoteIdentities.value = new Set()
  activeIdentities.value = new Set()
  await nextTick()
  audioHost.value?.querySelectorAll('[data-study1-remote-audio]').forEach(node => node.remove())
  if (generation === connectionGeneration) connectionState.value = 'disconnected'
}

watch(
  () => [props.phase, props.phaseVersion],
  () => disconnectRoom(),
)

onMounted(checkMicrophone)
onUnmounted(() => {
  disposed = true
  disconnectRoom()
})
</script>

<template>
  <section class="voice-room" aria-labelledby="voice-room-title">
    <header>
      <div>
        <p class="eyebrow">{{ phase === 'PROXY_MEETING' ? 'Delegated discussion' : 'Synchronous discussion' }}</p>
        <h2 id="voice-room-title">Audio meeting</h2>
      </div>
      <span class="connection" :data-state="connectionState">{{ connectionState }}</span>
    </header>

    <div class="participants" aria-label="Meeting participants">
      <div
        v-for="participantRole in expectedRoles"
        :key="participantRole"
        class="participant"
        :class="{ active: activeIdentities.has(participantRole) }"
      >
        <span class="avatar" aria-hidden="true">{{ readableRole(participantRole) }}</span>
        <div>
          <strong>{{ readableRole(participantRole) }}</strong>
          <span>{{ participantRole === role ? 'you' : (remoteIdentities.has(participantRole) ? 'connected' : 'waiting') }}</span>
        </div>
      </div>
    </div>

    <div class="device-row">
      <label for="study1-microphone">Microphone</label>
      <select id="study1-microphone" v-model="selectedDeviceId" :disabled="connectionState !== 'disconnected'">
        <option v-if="!devices.length" value="">No microphone available</option>
        <option v-for="device in devices" :key="device.deviceId" :value="device.deviceId">
          {{ device.label || 'Microphone' }}
        </option>
      </select>
      <button class="icon-button secondary" type="button" title="Check microphone" @click="checkMicrophone">
        <RefreshCw :size="18" aria-hidden="true" />
        <span class="sr-only">Check microphone</span>
      </button>
    </div>

    <p v-if="deviceState === 'denied' || deviceState === 'missing'" class="room-error">{{ error || 'No microphone was detected.' }}</p>
    <p v-else-if="error" class="room-error">{{ error }}</p>

    <div class="room-controls">
      <button
        v-if="connectionState === 'disconnected'"
        data-test="join-audio"
        type="button"
        :disabled="!canJoin"
        @click="joinAudio"
      >
        <Headphones :size="18" aria-hidden="true" />
        Join audio
      </button>
      <template v-else>
        <button class="icon-button" type="button" :title="muted ? 'Unmute microphone' : 'Mute microphone'" @click="toggleMute">
          <MicOff v-if="!muted" :size="20" aria-hidden="true" />
          <Mic v-else :size="20" aria-hidden="true" />
          <span class="sr-only">{{ muted ? 'Unmute microphone' : 'Mute microphone' }}</span>
        </button>
        <button class="icon-button leave" type="button" title="Leave audio" @click="disconnectRoom">
          <PhoneOff :size="20" aria-hidden="true" />
          <span class="sr-only">Leave audio</span>
        </button>
      </template>
    </div>
    <div ref="audioHost" hidden />
  </section>
</template>

<style scoped>
.voice-room { display:grid; gap:1.25rem; }
header { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; }
h2,.eyebrow { margin:0; }
h2 { font-size:1.35rem; letter-spacing:0; }
.eyebrow { color:#64717d; font-size:.78rem; font-weight:700; text-transform:uppercase; }
.connection { padding:.3rem .55rem; border:1px solid #c7d0d7; border-radius:6px; color:#52616d; font-size:.78rem; text-transform:capitalize; }
.connection[data-state="connected"] { border-color:#70a883; color:#17633c; background:#edf8f1; }
.participants { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.75rem; }
.participant { min-width:0; display:flex; align-items:center; gap:.65rem; padding:.75rem; border:1px solid #dce3e9; border-radius:7px; background:#fff; }
.participant.active { border-color:#2f7c5d; box-shadow:inset 3px 0 #2f7c5d; }
.participant div { min-width:0; display:grid; }
.participant strong,.participant span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.participant div span { color:#6a7782; font-size:.76rem; }
.avatar { flex:0 0 36px; width:36px; height:36px; display:grid; place-items:center; border-radius:50%; background:#e8edf1; color:#31414e; font-size:.78rem; font-weight:800; }
.device-row { display:grid; grid-template-columns:auto minmax(0,1fr) 40px; align-items:center; gap:.75rem; }
select { min-width:0; width:100%; padding:.62rem; border:1px solid #bac6d0; border-radius:6px; background:#fff; color:#263746; font:inherit; }
.room-controls { min-height:44px; display:flex; justify-content:center; gap:.65rem; }
button { display:inline-flex; align-items:center; justify-content:center; gap:.5rem; min-height:40px; border:0; border-radius:7px; padding:.65rem .9rem; background:#245f8e; color:#fff; font:inherit; font-weight:700; cursor:pointer; }
button:disabled { opacity:.45; cursor:not-allowed; }
.icon-button { width:42px; padding:0; }
.secondary { background:#e9eef2; color:#334551; }
.leave { background:#a13838; }
.room-error { margin:0; padding:.65rem .8rem; border-radius:6px; background:#fff0f0; color:#922; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
@media (max-width:620px) {
  .participants { grid-template-columns:1fr; }
  .device-row { grid-template-columns:1fr 40px; }
  .device-row label { grid-column:1/-1; }
}
</style>
