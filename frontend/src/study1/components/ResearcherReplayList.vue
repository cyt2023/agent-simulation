<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  busy: { type: Boolean, default: false },
  markers: { type: Array, default: () => [] },
  replayPlans: { type: Array, default: () => [] },
})

const emit = defineEmits(['create-marker', 'create-replay-plan'])

const researcherMarker = ref({
  type: 'technical',
  start_second: 0,
  end_second: 0,
  reason: '',
  participant_visible: false,
})
const replayPlanForm = ref({
  marker_ids: '',
  context_seconds: 10,
})
const markerTypes = [
  { value: 'technical', label: 'Technical' },
  { value: 'other', label: 'Other' },
  { value: 'confusing', label: 'Confusing' },
  { value: 'unexpected', label: 'Unexpected' },
  { value: 'uncomfortable', label: 'Uncomfortable' },
  { value: 'key_decision', label: 'Key decision' },
]
const canSubmitResearcherMarker = computed(() => (
  !props.busy
  && researcherMarker.value.type
  && researcherMarker.value.reason.trim()
  && Number(researcherMarker.value.start_second) >= 0
  && Number(researcherMarker.value.end_second) >= Number(researcherMarker.value.start_second)
))
const canSubmitReplayPlan = computed(() => (
  !props.busy
  && replayPlanForm.value.marker_ids.trim()
))

function submitResearcherMarker() {
  if (!canSubmitResearcherMarker.value) return
  emit('create-marker', {
    type: researcherMarker.value.type,
    start_ms: Math.round(Number(researcherMarker.value.start_second) * 1000),
    end_ms: Math.round(Number(researcherMarker.value.end_second) * 1000),
    reason: researcherMarker.value.reason.trim(),
    participant_visible: Boolean(researcherMarker.value.participant_visible),
  })
}

function submitReplayPlan() {
  if (!canSubmitReplayPlan.value) return
  emit('create-replay-plan', {
    marker_ids: replayPlanForm.value.marker_ids
      .split(',')
      .map(item => item.trim())
      .filter(Boolean),
    context_seconds: Number(replayPlanForm.value.context_seconds) || 0,
  })
}
</script>

<template>
  <section class="panel audit-panel">
    <h2>Markers and replay</h2>
    <form class="audit-form" @submit.prevent="submitResearcherMarker">
      <h3>Create researcher marker</h3>
      <div class="audit-form-grid">
        <label>
          Marker type
          <select v-model="researcherMarker.type" data-test="researcher-marker-type">
            <option v-for="type in markerTypes" :key="type.value" :value="type.value">
              {{ type.label }}
            </option>
          </select>
        </label>
        <label>
          Start second
          <input v-model.number="researcherMarker.start_second" data-test="researcher-marker-start" type="number" min="0">
        </label>
        <label>
          End second
          <input v-model.number="researcherMarker.end_second" data-test="researcher-marker-end" type="number" min="0">
        </label>
      </div>
      <label>
        Reason
        <textarea v-model="researcherMarker.reason" data-test="researcher-marker-reason" rows="3" />
      </label>
      <label class="toggle-row">
        <input v-model="researcherMarker.participant_visible" data-test="researcher-marker-visible" type="checkbox">
        Visible to participants
      </label>
      <button data-test="researcher-marker-submit" :disabled="!canSubmitResearcherMarker" type="submit">
        Save researcher marker
      </button>
    </form>

    <form class="audit-form replay-form" @submit.prevent="submitReplayPlan">
      <h3>Create replay plan</h3>
      <div class="audit-form-grid">
        <label>
          Marker IDs
          <input
            v-model="replayPlanForm.marker_ids"
            data-test="researcher-replay-marker-ids"
            placeholder="marker-1, marker-2"
          >
        </label>
        <label>
          Context seconds
          <input
            v-model.number="replayPlanForm.context_seconds"
            data-test="researcher-replay-context"
            type="number"
            min="0"
            max="300"
          >
        </label>
      </div>
      <button data-test="researcher-replay-submit" :disabled="!canSubmitReplayPlan" type="submit">
        Generate replay plan
      </button>
    </form>

    <div class="audit-grid">
      <div>
        <h3>Markers</h3>
        <p>{{ markers.length }} marker(s) captured for this session.</p>
      </div>
      <div>
        <h3>Replay plans</h3>
        <p>{{ replayPlans.length }} replay plan(s) generated for this session.</p>
      </div>
    </div>

    <ul v-if="markers.length" class="audit-list">
      <li v-for="marker in markers" :key="marker.marker_id">
        <strong>{{ marker.type || marker.marker_type }}</strong>
        <span>{{ Math.round((marker.start_ms || 0) / 1000) }}s - {{ Math.round((marker.end_ms || 0) / 1000) }}s</span>
        <p>{{ marker.reason }}</p>
      </li>
    </ul>
    <ul v-if="replayPlans.length" class="audit-list">
      <li v-for="plan in replayPlans" :key="plan.replay_plan_id">
        <strong>Replay plan {{ plan.version }}</strong>
        <span>{{ plan.items?.length || 0 }} item(s)</span>
        <p>{{ plan.items?.map(item => `${item.start_second}-${item.end_second}s`).join(', ') }}</p>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.panel { background:#f9fbfc; border:1px solid #dce3e9; border-radius:12px; padding:1.25rem; margin:1.25rem 0; }
.audit-form { display:grid; gap:1rem; margin-bottom:1.25rem; padding:1rem; border:1px solid #dce3e9; border-radius:10px; background:#fff; }
.audit-form h3 { margin:0; }
.audit-form-grid,.audit-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:1rem; }
label { display:grid; gap:.4rem; margin:.8rem 0; font-weight:650; }
input,textarea,select { padding:.65rem; border:1px solid #bac6d0; border-radius:7px; font:inherit; }
.toggle-row { display:flex; align-items:center; gap:.55rem; font-weight:600; }
button { width:max-content; border:0; border-radius:7px; padding:.65rem .9rem; background:#265f8c; color:white; font-weight:700; cursor:pointer; }
button:disabled { opacity:.42; cursor:not-allowed; }
.audit-list { display:grid; gap:.65rem; margin:1rem 0 0; padding:0; list-style:none; }
.audit-list li { padding:.75rem; border:1px solid #dce3e9; border-radius:8px; background:#fff; display:grid; gap:.25rem; }
.audit-list strong { text-transform:capitalize; }
.audit-list span { color:#667786; font-size:.85rem; }
</style>
