<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { CheckCircle2, Clock3 } from '@lucide/vue'

const props = defineProps({
  phase: { type: String, required: true },
  status: { type: String, default: 'waiting' },
  ready: { type: Boolean, default: false },
  remainingSeconds: { type: Number, default: 0 },
  sessionId: { type: String, default: '' },
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
const phaseGroups = [
  {
    key: 'preparation',
    label: 'Preparation',
    phases: ['SETUP', 'MATERIAL_READING', 'PRE_VOTE'],
  },
  {
    key: 'proxy_setup',
    label: 'Proxy setup',
    phases: ['PROXY_CONFIGURATION'],
  },
  {
    key: 'delegated_discussion',
    label: 'Delegated discussion',
    phases: ['PROXY_MEETING', 'TENTATIVE_DECISION'],
  },
  {
    key: 'review_handoff',
    label: 'Review and handoff',
    phases: [
      'DELEGATION_EXPECTATION',
      'REVIEW',
      'COMPREHENSION_MEASUREMENT',
      'HANDOFF',
    ],
  },
  {
    key: 'team_completion',
    label: 'Team completion',
    phases: [
      'SYNC_MEETING',
      'FINAL_DECISION',
      'FOLLOWUP_TASK',
      'POST_SURVEY',
      'COMPLETED',
    ],
  },
]
const currentStageIndex = computed(() => (
  phaseGroups.findIndex(group => group.phases.includes(props.phase))
))
const stagePosition = computed(() => {
  return currentStageIndex.value >= 0
    ? `Stage ${currentStageIndex.value + 1} of ${phaseGroups.length}`
    : 'Study stage'
})
const formattedTime = computed(() => {
  const minutes = Math.floor(displayedSeconds.value / 60)
  const seconds = displayedSeconds.value % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})
function phaseState(stageIndex) {
  if (stageIndex < currentStageIndex.value) return 'completed'
  if (stageIndex === currentStageIndex.value) return 'current'
  return 'upcoming'
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
    <div class="phase-copy">
      <span class="eyebrow">Study 1 / {{ sessionId ? `Session ${sessionId}` : stagePosition }}</span>
      <h1>{{ labels[phase] || phase }}</h1>
      <p>{{ descriptions[phase] || 'Follow the researcher instructions for this stage.' }}</p>
    </div>
    <div class="phase-state">
      <span class="status">{{ status }}</span>
      <span v-if="ready" class="ready"><CheckCircle2 :size="15" aria-hidden="true" />Ready for researcher</span>
      <span v-if="displayedSeconds > 0" data-test="phase-timer" class="timer">
        <Clock3 :size="15" aria-hidden="true" />{{ formattedTime }}
      </span>
    </div>
    <ol class="phase-rail" aria-label="Study phases">
      <li
        v-for="(group, index) in phaseGroups"
        :key="group.key"
        data-test="phase-rail-item"
        :data-state="phaseState(index)"
        :aria-current="phaseState(index) === 'current' ? 'step' : undefined"
        :title="group.label"
      >
        <span class="rail-marker">{{ index + 1 }}</span>
        <span class="rail-label">{{ group.label }}</span>
      </li>
    </ol>
  </header>
</template>

<style scoped>
.phase-header { min-height:92px; display:grid; grid-template-columns:minmax(0,1fr) auto; gap:.8rem 1.25rem; align-items:center; padding:.9rem 1.15rem .75rem; border:1px solid #d7dfe4; border-radius:7px; background:#fff; }
.phase-copy { min-width:0; }
.eyebrow { color:#526172; font-size:.74rem; font-weight:800; letter-spacing:0; text-transform:uppercase; }
h1 { margin:.2rem 0 0; font-size:1.45rem; color:#162534; letter-spacing:0; }
.phase-header p { max-width:650px; margin:.35rem 0 0; color:#62717e; font-size:.84rem; line-height:1.45; }
.phase-state { display:flex; align-items:flex-end; justify-content:center; gap:.4rem; flex-wrap:wrap; }
.status,.ready,.timer { min-height:30px; display:inline-flex; align-items:center; gap:.3rem; border-radius:5px; padding:.3rem .55rem; font-size:.76rem; background:#edf1f5; white-space:nowrap; }
.status { color:#4c5e69; text-transform:capitalize; }
.timer { color:#244f72; background:#e7f1f8; font-variant-numeric:tabular-nums; font-weight:800; }
.ready { background:#dff5e8; color:#12643a; }
.phase-rail { grid-column:1/-1; min-width:0; display:grid; grid-template-columns:repeat(5,minmax(110px,1fr)); gap:0; margin:.15rem 0 0; padding:0; overflow-x:auto; list-style:none; }
.phase-rail li { position:relative; min-width:110px; display:grid; justify-items:center; gap:.25rem; color:#82909a; font-size:.68rem; text-align:center; }
.phase-rail li::before { content:''; position:absolute; top:11px; left:0; right:0; height:2px; background:#d9e0e4; }
.phase-rail li:first-child::before { left:50%; }
.phase-rail li:last-child::before { right:50%; }
.rail-marker { position:relative; z-index:1; width:23px; height:23px; display:grid; place-items:center; border:2px solid #ccd5da; border-radius:50%; background:#fff; color:#64747e; font-size:.64rem; font-weight:800; }
.rail-label { width:100%; white-space:normal; line-height:1.25; }
.phase-rail li[data-state='completed']::before { background:#5f8d7d; }
.phase-rail li[data-state='completed'] .rail-marker { border-color:#5f8d7d; background:#5f8d7d; color:#fff; }
.phase-rail li[data-state='current'] { color:#184e61; font-weight:800; }
.phase-rail li[data-state='current'] .rail-marker { border-color:#26708b; background:#e8f3f6; color:#184e61; }
@media (max-width:640px) { .phase-header { grid-template-columns:1fr; align-items:flex-start; } .phase-state { justify-content:flex-start; align-items:center; } .phase-rail { grid-column:1; } }
</style>
