<script setup>
import { computed, onMounted, ref } from 'vue'

import MarkerDialog from './MarkerDialog.vue'
import {
  createMarker as apiCreateMarker,
  fetchMarkers as apiFetchMarkers,
} from '../services/study1Api.js'

const props = defineProps({
  sessionId: { type: String, required: true },
  initialOpen: { type: Boolean, default: false },
  fetchMarkers: { type: Function, default: apiFetchMarkers },
  createMarker: { type: Function, default: apiCreateMarker },
})

const markers = ref([])
const dialogOpen = ref(props.initialOpen)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const sortedMarkers = computed(() => [...markers.value].sort((left, right) => (
  Number(left.start_ms || 0) - Number(right.start_ms || 0)
)))

async function loadMarkers() {
  try {
    const result = await props.fetchMarkers(props.sessionId)
    markers.value = result.markers || []
  } catch (reason) {
    error.value = reason?.message || 'Unable to load markers.'
  }
}

async function submitMarker(payload) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await props.createMarker(props.sessionId, payload)
    notice.value = 'Marker saved.'
    dialogOpen.value = false
    await loadMarkers()
  } catch (failure) {
    error.value = failure?.message || 'Unable to save marker.'
  } finally {
    busy.value = false
  }
}

function markerLabel(value) {
  return {
    confusing: 'Confusing',
    unexpected: 'Unexpected',
    uncomfortable: 'Uncomfortable',
    key_decision: 'Key decision',
  }[value] || String(value || 'Marker')
}

function seconds(milliseconds) {
  return Math.round((Number(milliseconds) || 0) / 1000)
}

onMounted(loadMarkers)
</script>

<template>
  <section class="post-session-markers">
    <div class="section-heading">
      <div>
        <h2>Post-session markers</h2>
        <p class="muted">Mark moments for the follow-up interview. Markers are timestamped and saved with your role.</p>
      </div>
      <button type="button" data-test="open-marker-dialog" @click="dialogOpen = true">
        Add marker
      </button>
    </div>

    <p v-if="notice" class="success">{{ notice }}</p>
    <p v-if="error" class="error">{{ error }}</p>

    <MarkerDialog
      :open="dialogOpen"
      :busy="busy"
      @close="dialogOpen = false"
      @submit="submitMarker"
    />

    <ul v-if="sortedMarkers.length" class="marker-list">
      <li v-for="marker in sortedMarkers" :key="marker.marker_id">
        <strong>{{ markerLabel(marker.type || marker.marker_type) }}</strong>
        <span>{{ seconds(marker.start_ms) }}s-{{ seconds(marker.end_ms) }}s</span>
        <p>{{ marker.reason }}</p>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.post-session-markers { display:grid; gap:1rem; margin-top:1.25rem; padding-top:1.25rem; border-top:1px solid #dce3e9; }
.section-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; }
h2,p { margin:0; }
button { width:max-content; border:0; border-radius:8px; background:#245f8e; color:white; padding:.7rem 1rem; font:inherit; font-weight:700; cursor:pointer; }
.marker-list { display:grid; gap:.65rem; margin:0; padding:0; list-style:none; }
.marker-list li { padding:.75rem; border:1px solid #dce3e9; border-radius:7px; background:#fff; }
.marker-list strong { display:block; }
.marker-list span { color:#667482; font-size:.85rem; }
.marker-list p { margin-top:.35rem; }
.muted { color:#667482; line-height:1.45; }
.success { padding:.65rem .8rem; border-radius:7px; background:#e9f7ef; color:#17633c; }
.error { padding:.65rem .8rem; border-radius:7px; background:#fff0f0; color:#9b2828; }
@media (max-width:640px) {
  .section-heading { display:grid; }
}
</style>
