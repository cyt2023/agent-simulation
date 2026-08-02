<script setup>
import { computed } from 'vue'

import ParticipantSeat from './ParticipantSeat.vue'
import Study1VoiceRoom from './Study1VoiceRoom.vue'
import StudyTaskPanel from './StudyTaskPanel.vue'

const props = defineProps({
  sessionId: { type: String, required: true },
  phase: { type: String, required: true },
  phaseVersion: { type: Number, required: true },
  role: { type: String, required: true },
  audioSession: { type: Object, required: true },
  taskTitle: { type: String, default: 'Current study step' },
  taskDescription: { type: String, default: '' },
  remainingSeconds: { type: Number, default: 0 },
})
const emit = defineEmits(['error'])

const delegated = computed(() => props.phase === 'PROXY_MEETING')
const bridgeWaiting = computed(() => (
  ['teammate_1', 'teammate_2'].includes(props.role)
  && !['PROXY_MEETING', 'HANDOFF', 'SYNC_MEETING'].includes(props.phase)
))
const seats = computed(() => (
  delegated.value
    ? [
        { role: 'teammate_1', label: 'T1' },
        { role: 'proxy', label: 'AI Proxy for P', proxy: true },
        { role: 'teammate_2', label: 'T2' },
      ]
    : bridgeWaiting.value
      ? [
          { role: 'teammate_1', label: 'T1' },
          {
            role: 'bridge_placeholder',
            label: 'Meeting transition',
            placeholder: true,
          },
          { role: 'teammate_2', label: 'T2' },
        ]
      : [
        { role: 'principal', label: 'P' },
        { role: 'teammate_1', label: 'T1' },
        { role: 'teammate_2', label: 'T2' },
      ]
))
const formattedTime = computed(() => {
  const seconds = Math.max(0, Number(props.remainingSeconds) || 0)
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
})

function valueOf(source, fallback) {
  if (source && typeof source === 'object' && 'value' in source) return source.value
  return source ?? fallback
}

const connectionState = computed(() => valueOf(props.audioSession.connectionState, 'disconnected'))
const reconnectSeconds = computed(() => valueOf(props.audioSession.reconnectSecondsRemaining, 0))
const muted = computed(() => Boolean(valueOf(props.audioSession.muted, false)))
const remotes = computed(() => valueOf(props.audioSession.remoteIdentities, new Set()))
const active = computed(() => valueOf(props.audioSession.activeIdentities, new Set()))

function seatState(seat) {
  if (seat.placeholder) return 'unavailable'
  if (connectionState.value !== 'connected') return 'waiting'
  if (seat.role === props.role || remotes.value.has(seat.role)) return 'connected'
  return 'waiting'
}
</script>

<template>
  <section class="meeting-workspace" :data-phase="phase">
    <div class="meeting-stage">
      <header class="meeting-heading">
        <div>
          <span>{{ delegated ? 'Delegated discussion' : bridgeWaiting ? 'Connection held' : 'Synchronous discussion' }}</span>
          <h2>{{ delegated ? 'T1, the AI Proxy, and T2' : bridgeWaiting ? 'T1 and T2 remain connected' : 'P, T1, and T2' }}</h2>
        </div>
        <strong class="meeting-clock">{{ remainingSeconds > 0 ? formattedTime : 'Audio meeting' }}</strong>
      </header>
      <div class="meeting-status-strip" role="status">
        <span>{{ connectionState.replace('_', ' ') }}</span>
        <span>{{ phase.replaceAll('_', ' ') }}</span>
        <span>Role: {{ role.replaceAll('_', ' ') }}</span>
      </div>
      <div class="seat-grid">
        <ParticipantSeat
          v-for="seat in seats"
          :key="seat.role"
          :role="seat.role"
          :label="seat.label"
          :proxy="seat.proxy"
          :placeholder="seat.placeholder"
          :local="seat.role === role"
          :muted="seat.role === role && muted"
          :active="!seat.placeholder && active.has(seat.role)"
          :state="seatState(seat)"
        />
      </div>
      <Study1VoiceRoom
        :session-id="sessionId"
        :phase="phase"
        :phase-version="phaseVersion"
        :role="role"
        :audio-session="audioSession"
        :show-roster="false"
        embedded
        @error="emit('error', $event)"
      />
    </div>
    <StudyTaskPanel :title="taskTitle" :description="taskDescription">
      <slot />
    </StudyTaskPanel>
    <p v-if="connectionState === 'reconnecting'" class="sr-status" role="status">
      Reconnecting audio - {{ reconnectSeconds }}s
    </p>
  </section>
</template>

<style scoped>
.meeting-workspace { display:grid; grid-template-columns:minmax(0,4fr) minmax(230px,1fr); min-height:500px; overflow:hidden; border:1px solid #cfd7dc; border-radius:7px; background:#fff; }
.meeting-stage { min-width:0; display:grid; grid-template-rows:auto auto 1fr auto; background:#182126; color:#eef3f4; }
.meeting-heading { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding:1rem 1.15rem; border-bottom:1px solid #354148; background:#182126; }
.meeting-heading span { color:#94a5ad; font-size:.72rem; font-weight:800; text-transform:uppercase; }
.meeting-heading h2 { margin:.2rem 0 0; font-size:1.05rem; color:#f5f7f8; }
.meeting-clock { flex:none; color:#dce8eb; font-size:.88rem; font-variant-numeric:tabular-nums; }
.meeting-status-strip { display:flex; justify-content:space-between; gap:.75rem; padding:.55rem 1.15rem; border-bottom:1px solid #354148; background:#222d32; color:#aebcc2; font-size:.7rem; text-transform:capitalize; }
.seat-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.8rem; align-content:center; padding:1.35rem; }
.sr-status { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); }
@media (max-width:860px) { .meeting-workspace { grid-template-columns:1fr; } }
@media (max-width:680px) { .seat-grid { grid-template-columns:1fr; padding:.85rem; } .meeting-heading { align-items:flex-start; } .meeting-status-strip { flex-wrap:wrap; } }
</style>
