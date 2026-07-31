<script setup>
import { computed, onMounted, ref } from 'vue'

import {
  createMarker as apiCreateMarker,
  fetchMarkers as apiFetchMarkers,
} from '../services/study1Api.js'

const props = defineProps({
  sessionId: { type: String, required: true },
  fetchMarkers: { type: Function, default: apiFetchMarkers },
  createMarker: { type: Function, default: apiCreateMarker },
})

const markerType = ref('confusing')
const startSeconds = ref(0)
const endSeconds = ref(0)
const reason = ref('')
const markers = ref([])
const busy = ref(false)
const error = ref('')
const notice = ref('')

const markerTypes = [
  { value: 'confusing', label: 'Confusing' },
  { value: 'unexpected', label: 'Unexpected' },
  { value: 'uncomfortable', label: 'Uncomfortable' },
  { value: 'key_decision', label: 'Key decision' },
]

const canSubmit = computed(() => (
  !busy.value
  && markerType.value
  && reason.value.trim()
  && Number(startSeconds.value) >= 0
  && Number(endSeconds.value) >= Number(startSeconds.value)
))

async function loadMarkers() {
  try {
    const result = await props.fetchMarkers(props.sessionId)
    markers.value = result.markers || []
  } catch (reason) {
    error.value = reason?.message || 'Unable to load markers.'
  }
}

async function submitMarker() {
  if (!canSubmit.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await props.createMarker(props.sessionId, {
      type: markerType.value,
      start_ms: Math.round(Number(startSeconds.value) * 1000),
      end_ms: Math.round(Number(endSeconds.value) * 1000),
      reason: reason.value.trim(),
    })
    notice.value = 'Marker saved.'
    reason.value = ''
    await loadMarkers()
  } catch (failure) {
    error.value = failure?.message || 'Unable to save marker.'
  } finally {
    busy.value = false
  }
}

function markerLabel(value) {
  return markerTypes.find(type => type.value === value)?.label || String(value || 'Marker')
}

function seconds(milliseconds) {
  return Math.round((Number(milliseconds) || 0) / 1000)
}
</script>

<template>
  <section class="marker-phase">
    <h2>Post-session markers</h2>
    <p class="muted">Mark moments for the follow-up interview. Markers are timestamped and saved with your role.</p>
    <p v-if="notice" class="success">{{ notice }}</p>
    <p v-if="error" class="error">{{ error }}</p>
    <div class="marker-grid">
      <label>
        Marker type
        <select v-model="markerType" data-test="marker-type">
          <option v-for="type in markerTypes" :key="type.value" :value="type.value">
            {{ type.label }}
          </option>
        </select>
      </label>
      <label>
        Start second
        <input v-model.number="startSeconds" data-test="marker-start" type="number" min="0">
      </label>
      <label>
        End second
        <input v-model.number="endSeconds" data-test="marker-end" type="number" min="0">
      </label>
    </div>
    <label>
      Reason
      <textarea v-model="reason" data-test="marker-reason" rows="3" />
    </label>
    <button data-test="submit-marker" :disabled="!canSubmit" @click="submitMarker">
      Save marker
    </button>

    <ul v-if="markers.length" class="marker-list">
      <li v-for="marker in markers" :key="marker.marker_id">
        <strong>{{ markerLabel(marker.type || marker.marker_type) }}</strong>
        <span>{{ seconds(marker.start_ms) }}s-{{ seconds(marker.end_ms) }}s</span>
        <p>{{ marker.reason }}</p>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.marker-phase { display:grid; gap:1rem; margin-top:1.25rem; padding-top:1.25rem; border-top:1px solid #dce3e9; }
h2,p { margin:0; }
label { display:grid; gap:.45rem; font-weight:650; }
input,textarea,select { padding:.7rem; border:1px solid #bbc6d1; border-radius:7px; font:inherit; }
button { width:max-content; }
.marker-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:.85rem; }
.marker-list { display:grid; gap:.65rem; margin:0; padding:0; list-style:none; }
.marker-list li { padding:.75rem; border:1px solid #dce3e9; border-radius:7px; background:#fff; }
.marker-list strong { display:block; }
.marker-list span { color:#667482; font-size:.85rem; }
.marker-list p { margin-top:.35rem; }
.muted { color:#667482; line-height:1.45; }
.success { padding:.65rem .8rem; border-radius:7px; background:#e9f7ef; color:#17633c; }
.error { padding:.65rem .8rem; border-radius:7px; background:#fff0f0; color:#9b2828; }
</style>
