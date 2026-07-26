<script setup>
defineProps({
  phase: { type: String, required: true },
  status: { type: String, default: 'waiting' },
  ready: { type: Boolean, default: false },
})

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
</script>

<template>
  <header class="phase-header">
    <div>
      <span class="eyebrow">Study 1</span>
      <h1>{{ labels[phase] || phase }}</h1>
    </div>
    <div class="phase-state">
      <span class="status">{{ status }}</span>
      <span v-if="ready" class="ready">Ready for researcher</span>
    </div>
  </header>
</template>

<style scoped>
.phase-header { display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; border-bottom:1px solid #dce2e8; padding-bottom:1rem; }
.eyebrow { color:#526172; font-size:.78rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
h1 { margin:.25rem 0 0; font-size:1.65rem; color:#162534; }
.phase-state { display:flex; flex-direction:column; align-items:flex-end; gap:.35rem; }
.status,.ready { border-radius:999px; padding:.3rem .65rem; font-size:.78rem; background:#edf1f5; }
.ready { background:#dff5e8; color:#12643a; }
</style>
