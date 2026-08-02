<script setup>
import { onMounted, ref } from 'vue'
import { AlertCircle, CheckCircle2, RefreshCw } from '@lucide/vue'

import { reportMediaDevice } from '../services/study1Api.js'
import { displayMicrophoneLabel } from '../services/uiLabels.js'

const props = defineProps({
  sessionId: { type: String, required: true },
})

const state = ref('checking')
const deviceLabel = ref('')
const error = ref('')

async function checkDevice() {
  state.value = 'checking'
  error.value = ''
  let report = { state: 'error', device: {} }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    stream.getTracks().forEach(track => track.stop())
    const microphones = (await navigator.mediaDevices.enumerateDevices())
      .filter(device => device.kind === 'audioinput')
    if (!microphones.length) {
      state.value = 'missing'
      error.value = 'No microphone was detected.'
      report = { state: 'missing', device: {} }
    } else {
      state.value = 'ready'
      deviceLabel.value = microphones[0].label || 'Microphone'
      report = {
        state: 'ready',
        device: { kind: 'audioinput', label: deviceLabel.value },
      }
    }
  } catch (reason) {
    state.value = 'denied'
    error.value = reason?.message || 'Microphone permission was denied.'
    report = { state: 'denied', device: {} }
  }
  try {
    await reportMediaDevice(props.sessionId, report)
  } catch (reason) {
    error.value = reason?.message || 'Unable to report microphone status.'
  }
}

onMounted(checkDevice)
</script>

<template>
  <section class="device-check" aria-labelledby="device-check-title">
    <div class="device-icon" :data-state="state">
      <CheckCircle2 v-if="state === 'ready'" :size="22" aria-hidden="true" />
      <RefreshCw v-else-if="state === 'checking'" :size="22" aria-hidden="true" />
      <AlertCircle v-else :size="22" aria-hidden="true" />
    </div>
    <div>
      <h2 id="device-check-title">Microphone check</h2>
      <p v-if="state === 'checking'">Checking microphone access...</p>
      <p v-else-if="state === 'ready'"><strong>{{ displayMicrophoneLabel(deviceLabel, 0) }}</strong> is ready.</p>
      <p v-else>{{ error }}</p>
    </div>
    <button type="button" :disabled="state === 'checking'" @click="checkDevice">
      <RefreshCw :size="17" aria-hidden="true" />
      Check again
    </button>
  </section>
</template>

<style scoped>
.device-check { display:grid; grid-template-columns:42px minmax(0,1fr) auto; align-items:center; gap:.85rem; padding-bottom:1.25rem; margin-bottom:1.25rem; border-bottom:1px solid #dce3e9; }
.device-icon { width:42px; height:42px; display:grid; place-items:center; border-radius:50%; background:#eef2f4; color:#5c6b76; }
.device-icon[data-state="ready"] { background:#e7f5ed; color:#24704b; }
.device-icon[data-state="denied"],.device-icon[data-state="missing"] { background:#fff0f0; color:#9b2828; }
h2,p { margin:0; }
h2 { font-size:1rem; letter-spacing:0; }
p { margin-top:.2rem; color:#667482; }
button { display:inline-flex; align-items:center; gap:.4rem; border:1px solid #aebbc5; border-radius:6px; padding:.55rem .7rem; background:#fff; color:#334754; font:inherit; font-weight:700; cursor:pointer; }
button:disabled { opacity:.5; cursor:not-allowed; }
@media (max-width:560px) { .device-check { grid-template-columns:42px minmax(0,1fr); } button { grid-column:1/-1; justify-content:center; } }
</style>
