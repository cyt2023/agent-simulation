<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { createReviewTelemetry } from '../composables/useReviewTelemetry.js'
import {
  fetchReview,
  fetchStudy1Recording,
  logReviewUiEvent,
  sendReviewEventBatch,
} from '../services/study1Api.js'

const props = defineProps({ sessionId: { type: String, required: true } })
const loading = ref(true)
const error = ref('')
const summary = ref(null)
const transcript = ref(null)
const recordings = ref([])
const replayUrl = ref('')
const replayingId = ref('')
const transcriptExpanded = ref(false)
const maxDepth = ref(0)
const visitId = `review-${Date.now()}-${Math.random().toString(36).slice(2)}`
const telemetry = createReviewTelemetry({
  sessionId: props.sessionId,
  visitId,
  sendBatch: sendReviewEventBatch,
})
let heartbeatTimer = null
let scrollTimer = null

const transcriptSegments = computed(() => {
  const content = transcript.value?.content || ''
  try {
    const parsed = JSON.parse(content)
    if (Array.isArray(parsed)) {
      return parsed.map((segment, index) => {
        const sourceId = String(segment.segment_id || index + 1)
        return {
          id: `segment-${sourceId.replace(/[^A-Za-z0-9_-]/g, '-')}`,
          sourceId,
          text: `[${formatTime(segment.start_ms)}] ${roleLabel(segment.speaker)}: ${segment.text || ''}`,
        }
      })
    }
  } catch {
    // Older A artifacts stored one already-rendered segment per line.
  }
  return content.split(/\r?\n/).filter(Boolean).map((text, index) => ({
    id: `segment-${index + 1}`,
    sourceId: `legacy-${index + 1}`,
    text,
  }))
})

function formatTime(value) {
  const milliseconds = Math.max(0, Number(value) || 0)
  const minutes = Math.floor(milliseconds / 60000)
  const seconds = Math.floor((milliseconds % 60000) / 1000)
  const remainder = Math.floor(milliseconds % 1000)
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(remainder).padStart(3, '0')}`
}

function roleLabel(role) {
  return {
    principal: 'Human - Principal (P)',
    teammate_1: 'Human - Teammate 1 (T1)',
    teammate_2: 'Human - Teammate 2 (T2)',
    proxy: 'AI Proxy (X)',
  }[role] || role || 'Unknown'
}

function log(eventType, payload = {}) {
  return logReviewUiEvent(props.sessionId, eventType, payload).catch(() => {})
}

function markCritical(targetType, targetId) {
  const note = window.prompt('Optional note for this critical marker:', '') ?? ''
  log('critical_marker', { target_type: targetType, target_id: targetId, note })
}

async function replay(recordingId) {
  if (replayUrl.value) URL.revokeObjectURL(replayUrl.value)
  const blob = await fetchStudy1Recording(props.sessionId, recordingId)
  replayUrl.value = URL.createObjectURL(blob)
  replayingId.value = recordingId
  await telemetry.replayRange({ recording_id: recordingId, start_ms: 0, end_ms: 0 })
  await log('recording_replay', { recording_id: recordingId, action: 'play' })
  await nextTick()
  document.querySelector('[data-study1-replay]')?.play()
}

function toggleTranscript() {
  transcriptExpanded.value = !transcriptExpanded.value
  telemetry.transcriptToggle(transcriptExpanded.value)
  log(transcriptExpanded.value ? 'transcript_expand' : 'transcript_collapse')
}

function handleScroll() {
  if (scrollTimer) return
  scrollTimer = window.setTimeout(() => {
    scrollTimer = null
    const element = document.documentElement
    const available = Math.max(1, element.scrollHeight - window.innerHeight)
    maxDepth.value = Math.max(maxDepth.value, Math.min(1, window.scrollY / available))
    const visible = transcriptExpanded.value
      ? transcriptSegments.value
          .filter(segment => {
            const node = document.getElementById(segment.id)
            if (!node) return false
            const rect = node.getBoundingClientRect()
            return rect.bottom >= 0 && rect.top <= window.innerHeight
          })
          .map(segment => segment.sourceId)
      : []
    telemetry.scroll({ max_depth: maxDepth.value, visible_segments: visible })
    log('scroll_depth', { max_depth: maxDepth.value, visible_segments: visible })
  }, 750)
}

function handleVisibilityChange() {
  telemetry.visibility(document.visibilityState === 'hidden' ? 'hidden' : 'visible')
}

function handleFocus() {
  telemetry.focus(true)
}

function handleBlur() {
  telemetry.focus(false)
}

onMounted(async () => {
  telemetry.enter()
  heartbeatTimer = window.setInterval(() => telemetry.heartbeat(), 5000)
  window.addEventListener('scroll', handleScroll, { passive: true })
  document.addEventListener('visibilitychange', handleVisibilityChange)
  window.addEventListener('focus', handleFocus)
  window.addEventListener('blur', handleBlur)
  try {
    const result = await fetchReview(props.sessionId)
    summary.value = result.summary
    transcript.value = result.transcript
    try {
      recordings.value = JSON.parse(result.recording_manifest?.content || '[]')
    } catch {
      recordings.value = []
    }
    if (summary.value) await log('summary_visible')
  } catch (reason) {
    error.value = reason?.message || 'Review is not available.'
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  window.removeEventListener('focus', handleFocus)
  window.removeEventListener('blur', handleBlur)
  if (heartbeatTimer) window.clearInterval(heartbeatTimer)
  if (scrollTimer) window.clearTimeout(scrollTimer)
  telemetry.leave()
  log('active_reading_time', {
    client_active_seconds: telemetry.activeSeconds(),
    max_depth: maxDepth.value,
  })
  log('review_page_leave')
  if (replayUrl.value) URL.revokeObjectURL(replayUrl.value)
})
</script>

<template>
  <section>
    <h2>Review the delegated discussion</h2>
    <p v-if="loading">Loading the authorized artifact...</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <template v-else>
      <article class="summary">
        <div class="artifact-heading">
          <h3>Neutral summary</h3>
          <button class="marker" @click="markCritical('summary', summary?.artifact_id || 'summary')">Mark critical</button>
        </div>
        <p v-if="summary?.content">{{ summary.content }}</p>
        <p v-else>The summary artifact is not ready yet.</p>
      </article>
      <button class="transcript-toggle" :disabled="!transcript" @click="toggleTranscript">
        {{ transcriptExpanded ? 'Collapse transcript' : 'Expand transcript' }}
      </button>
      <div v-if="transcriptExpanded" class="transcript">
        <p
          v-for="segment in transcriptSegments"
          :id="segment.id"
          :key="segment.id"
          @mouseenter="telemetry.segmentVisible(segment.sourceId); log('transcript_segment_view', { segment_id: segment.sourceId })"
        >
          {{ segment.text }}
          <button class="marker" @click="markCritical('transcript_segment', segment.sourceId)">Mark</button>
        </p>
      </div>
      <section v-if="recordings.length" class="recordings">
        <h3>Audio replay</h3>
        <button v-for="recording in recordings" :key="recording.recording_id" @click="replay(recording.recording_id)">
          Replay {{ roleLabel(recording.role || recording.speaker || recording.participant_id) }} ({{ Math.round((recording.duration_ms || 0) / 1000) }}s)
        </button>
        <audio
          v-if="replayUrl"
          data-study1-replay
          controls
          :src="replayUrl"
          @play="log('recording_replay', { recording_id: replayingId, action: 'playback_started' })"
        />
      </section>
    </template>
  </section>
</template>

<style scoped>
.summary { border-left:4px solid #5486ad; padding:.35rem 1rem; background:#f2f7fa; white-space:pre-wrap; }
.artifact-heading { display:flex; align-items:center; justify-content:space-between; gap:1rem; }
.artifact-heading h3 { margin-bottom:.25rem; }
.transcript-toggle { margin-top:1rem; }
.transcript { margin-top:1rem; border:1px solid #dbe3e9; border-radius:9px; padding:1rem; background:white; }
.transcript p { line-height:1.6; border-bottom:1px solid #edf0f2; padding-bottom:.65rem; }
.marker { float:right; padding:.3rem .55rem; font-size:.75rem; background:#63788a; }
.recordings { display:grid; gap:.65rem; margin-top:1rem; }
.recordings button { width:max-content; }
.recordings audio { width:100%; }
.error { color:#9b2828; }
</style>
