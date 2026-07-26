<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { fetchReview, logReviewUiEvent } from '../services/study1Api.js'

const props = defineProps({ sessionId: { type: String, required: true } })
const loading = ref(true)
const error = ref('')
const summary = ref(null)
const transcript = ref(null)
const transcriptExpanded = ref(false)
const maxDepth = ref(0)
const enteredAt = ref(0)
let scrollTimer = null

const transcriptSegments = computed(() => {
  const content = transcript.value?.content || ''
  return content.split(/\r?\n/).filter(Boolean).map((text, index) => ({
    id: `segment-${index + 1}`,
    text,
  }))
})

function log(eventType, payload = {}) {
  return logReviewUiEvent(props.sessionId, eventType, payload).catch(() => {})
}

function toggleTranscript() {
  transcriptExpanded.value = !transcriptExpanded.value
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
          .map(segment => segment.id)
      : []
    log('scroll_depth', { max_depth: maxDepth.value, visible_segments: visible })
  }, 750)
}

onMounted(async () => {
  enteredAt.value = Date.now()
  window.addEventListener('scroll', handleScroll, { passive: true })
  try {
    const result = await fetchReview(props.sessionId)
    summary.value = result.summary
    transcript.value = result.transcript
    if (summary.value) await log('summary_visible')
  } catch (reason) {
    error.value = reason?.message || 'Review is not available.'
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
  if (scrollTimer) window.clearTimeout(scrollTimer)
  log('active_reading_time', {
    client_active_seconds: Math.max(0, Math.round((Date.now() - enteredAt.value) / 1000)),
    max_depth: maxDepth.value,
  })
  log('review_page_leave')
})
</script>

<template>
  <section>
    <h2>Review the delegated discussion</h2>
    <p v-if="loading">Loading the authorized artifact…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <template v-else>
      <article class="summary">
        <h3>Neutral summary</h3>
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
          @mouseenter="log('transcript_segment_view', { segment_id: segment.id })"
        >
          {{ segment.text }}
        </p>
      </div>
    </template>
  </section>
</template>

<style scoped>
.summary { border-left:4px solid #5486ad; padding:.35rem 1rem; background:#f2f7fa; white-space:pre-wrap; }
.transcript-toggle { margin-top:1rem; }
.transcript { margin-top:1rem; border:1px solid #dbe3e9; border-radius:9px; padding:1rem; background:white; }
.transcript p { line-height:1.6; border-bottom:1px solid #edf0f2; padding-bottom:.65rem; }
.error { color:#9b2828; }
</style>
