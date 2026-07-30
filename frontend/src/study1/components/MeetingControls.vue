<script setup>
import { Headphones, LogIn, Mic, MicOff, PhoneOff, RefreshCw, Volume2 } from '@lucide/vue'

const props = defineProps({
  connectionState: { type: String, default: 'disconnected' },
  reconnectSeconds: { type: Number, default: 0 },
  muted: Boolean,
  canJoin: Boolean,
  busy: Boolean,
  outputDevices: { type: Array, default: () => [] },
  selectedOutputId: { type: String, default: '' },
  outputSupported: { type: Boolean, default: false },
  outputNotice: { type: String, default: '' },
})
const emit = defineEmits(['join', 'toggle-mute', 'leave', 'select-output'])
</script>

<template>
  <div class="meeting-controls" aria-label="Audio meeting controls">
    <p v-if="connectionState === 'reconnecting'" class="connection-note" role="status">
      <RefreshCw :size="16" aria-hidden="true" />
      Reconnecting audio - {{ reconnectSeconds }}s
    </p>
    <p v-else-if="connectionState === 'reconnect_failed'" class="connection-note failed" role="status">
      Audio reconnection timed out.
    </p>
    <button
      v-if="!['connected', 'reconnecting'].includes(connectionState)"
      data-test="join-audio"
      type="button"
      :disabled="busy || !canJoin"
      title="Join audio"
      @click="emit('join')"
    >
      <LogIn :size="19" aria-hidden="true" />
      Join audio
    </button>
    <template v-else>
      <button
        data-test="toggle-mute"
        class="icon-control"
        type="button"
        :disabled="busy || connectionState !== 'connected'"
        :title="muted ? 'Unmute microphone' : 'Mute microphone'"
        @click="emit('toggle-mute')"
      >
        <Mic v-if="muted" :size="20" aria-hidden="true" />
        <MicOff v-else :size="20" aria-hidden="true" />
        <span>{{ muted ? 'Unmute' : 'Mute' }}</span>
      </button>
      <span class="audio-state"><Headphones :size="17" aria-hidden="true" /> Audio only</span>
      <label v-if="outputSupported" class="output-control">
        <Volume2 :size="17" aria-hidden="true" />
        <span class="sr-only">Audio output</span>
        <select
          data-test="audio-output"
          :value="selectedOutputId"
          title="Audio output"
          @change="emit('select-output', $event.target.value)"
        >
          <option value="">System default</option>
          <option
            v-for="(device, index) in outputDevices"
            :key="device.deviceId"
            :value="device.deviceId"
          >
            {{ device.label || `Audio output ${index + 1}` }}
          </option>
        </select>
      </label>
      <span v-else class="output-note">
        Output selection is not supported by this browser.
      </span>
      <button
        class="icon-control leave"
        type="button"
        :disabled="busy"
        title="Leave audio"
        @click="emit('leave')"
      >
        <PhoneOff :size="20" aria-hidden="true" />
        <span>Leave</span>
      </button>
    </template>
    <p v-if="outputNotice" class="output-notice" role="status">{{ outputNotice }}</p>
  </div>
</template>

<style scoped>
.meeting-controls { min-height:58px; display:flex; align-items:center; justify-content:center; gap:.75rem; flex-wrap:wrap; padding:.8rem 1rem; border-top:1px solid #354148; background:#121a1e; }
button { min-height:40px; display:inline-flex; align-items:center; justify-content:center; gap:.45rem; border:0; border-radius:6px; padding:.6rem .85rem; background:#267b73; color:#fff; font:inherit; font-weight:700; cursor:pointer; }
button:disabled { opacity:.45; cursor:not-allowed; }
.icon-control { background:#222d32; color:#edf3f4; border:1px solid #4a585e; }
.leave { color:#ffd8d8; border-color:#7c4b4b; }
.audio-state,.connection-note { display:inline-flex; align-items:center; gap:.4rem; color:#acbbc1; font-size:.8rem; }
.output-control { display:flex; align-items:center; gap:.4rem; color:#b8c5ca; }
.output-control select { max-width:160px; min-height:36px; border:1px solid #4a585e; border-radius:6px; background:#222d32; color:#edf3f4; padding:.35rem .45rem; }
.output-note { max-width:180px; color:#98a8ae; font-size:.72rem; line-height:1.3; }
.output-notice { flex-basis:100%; margin:0; color:#8b4444; font-size:.75rem; text-align:center; }
.connection-note { margin:0; width:100%; justify-content:center; font-weight:700; }
.connection-note.failed { color:#ffb9b9; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
</style>
