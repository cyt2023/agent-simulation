<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps({
  phase: { type: String, required: true },
  status: { type: String, default: 'waiting' },
  ready: { type: Boolean, default: false },
  remainingSeconds: { type: Number, default: 0 },
})
const displayedSeconds = ref(Math.max(0, props.remainingSeconds || 0))
let timer = null

const labels = {
  SETUP: 'Setup',
  MATERIAL_READING: 'Material reading',
  PRE_VOTE: 'Initial judgment',
  PROXY_CONFIGURATION: 'Proxy configuration',
  PROXY_MEETING: 'Delegated discussion',
  TENTATIVE_DECISION: 'Tentative decision',
  DELEGATION_EXPECTATION: 'Delegation expectation',
  REVIEW: 'Review',
  COMPREHENSION_MEASUREMENT: 'Comprehension measurement',
  HANDOFF: 'Handoff',
  SYNC_MEETING: 'Synchronous meeting',
  FINAL_DECISION: 'Final decision',
  FOLLOWUP_TASK: 'Follow-up task',
  POST_SURVEY: 'Post survey',
  COMPLETED: 'Completed',
}
const descriptions = {
  SETUP: 'Confirm identity, consent, and device readiness.',
  MATERIAL_READING: 'Read only the private material assigned to your role.',
  PRE_VOTE: 'Record an independent judgment before discussion.',
  PROXY_CONFIGURATION: 'Lock X authority and material access, or confirm readiness.',
  PROXY_MEETING: 'T1 and T2 discuss with X while P remains isolated.',
  TENTATIVE_DECISION: 'T1 and T2 record the delegated discussion status.',
  DELEGATION_EXPECTATION: 'P records expectations before seeing the meeting record.',
  REVIEW: 'P reviews the fixed summary, transcript, and authorized replay.',
  COMPREHENSION_MEASUREMENT: 'P records understanding before rejoining.',
  HANDOFF: 'X leaves and P joins the existing T1/T2 audio connection.',
  SYNC_MEETING: 'P, T1, and T2 discuss together; X is absent.',
  FINAL_DECISION: 'Record the final individual or team decision.',
  FOLLOWUP_TASK: 'Complete the structured collaboration follow-up.',
  POST_SURVEY: 'Complete the final measurement.',
  COMPLETED: 'All required Study 1 stages are complete.',
}

watch(() => props.remainingSeconds, value => {
  displayedSeconds.value = Math.max(0, Number(value) || 0)
})
onMounted(() => {
  timer = window.setInterval(() => {
    if (props.status === 'running' && displayedSeconds.value > 0) displayedSeconds.value -= 1
  }, 1000)
})
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <header class="phase-header">
    <div>
      <span class="eyebrow">Study 1</span>
      <h1>{{ labels[phase] || phase }}</h1>
      <p>{{ descriptions[phase] || 'Follow the researcher instructions for this stage.' }}</p>
    </div>
    <div class="phase-state">
      <span class="status">{{ status }}</span>
      <span v-if="ready" class="ready">Ready for researcher</span>
      <span v-if="displayedSeconds > 0" class="timer">{{ displayedSeconds }}s remaining</span>
    </div>
  </header>
</template>

<style scoped>
.phase-header { display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; border-bottom:1px solid #dce2e8; padding-bottom:1rem; }
.eyebrow { color:#526172; font-size:.78rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
h1 { margin:.25rem 0 0; font-size:1.65rem; color:#162534; }
.phase-header p { max-width:620px; margin:.45rem 0 0; color:#62717e; font-size:.86rem; }
.phase-state { display:flex; flex-direction:column; align-items:flex-end; gap:.35rem; }
.status,.ready,.timer { border-radius:999px; padding:.3rem .65rem; font-size:.78rem; background:#edf1f5; }
.timer { color:#244f72; background:#e7f1f8; font-variant-numeric:tabular-nums; }
.ready { background:#dff5e8; color:#12643a; }
</style>
