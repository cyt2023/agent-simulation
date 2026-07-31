<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['submit'])

const form = ref({
  summary_artifact_id: '',
  omission_error: false,
  misattribution_error: false,
  hallucination_error: false,
  decision_status_error: false,
  action_item_error: false,
  note: '',
})

const needsNote = computed(() => (
  form.value.omission_error
  || form.value.misattribution_error
  || form.value.hallucination_error
  || form.value.decision_status_error
  || form.value.action_item_error
))
const canSubmit = computed(() => (
  !props.busy
  && form.value.summary_artifact_id.trim()
  && (!needsNote.value || form.value.note.trim())
))

function submit() {
  if (!canSubmit.value) return
  emit('submit', {
    summary_artifact_id: form.value.summary_artifact_id.trim(),
    ratings: {
      omission_error: Boolean(form.value.omission_error),
      misattribution_error: Boolean(form.value.misattribution_error),
      hallucination_error: Boolean(form.value.hallucination_error),
      decision_status_error: Boolean(form.value.decision_status_error),
      action_item_error: Boolean(form.value.action_item_error),
      note: form.value.note.trim(),
    },
  })
}
</script>

<template>
  <form class="audit-form summary-qa-form" @submit.prevent="submit">
    <h3>Summary QA</h3>
    <p class="muted">Record offline quality issues without changing what participants saw.</p>
    <div class="audit-form-grid">
      <label>
        Summary artifact ID
        <input v-model="form.summary_artifact_id" data-test="summary-qa-artifact-id">
      </label>
      <label class="toggle-row">
        <input v-model="form.omission_error" data-test="summary-qa-omission" type="checkbox">
        Omission error
      </label>
      <label class="toggle-row">
        <input v-model="form.misattribution_error" data-test="summary-qa-misattribution" type="checkbox">
        Misattribution error
      </label>
      <label class="toggle-row">
        <input v-model="form.hallucination_error" data-test="summary-qa-hallucination" type="checkbox">
        Hallucination error
      </label>
      <label class="toggle-row">
        <input v-model="form.decision_status_error" data-test="summary-qa-decision-status" type="checkbox">
        Decision status error
      </label>
      <label class="toggle-row">
        <input v-model="form.action_item_error" data-test="summary-qa-action-item" type="checkbox">
        Action item error
      </label>
    </div>
    <label>
      Note
      <textarea v-model="form.note" data-test="summary-qa-note" rows="3" />
    </label>
    <button data-test="summary-qa-submit" :disabled="!canSubmit" type="submit">
      Save summary QA
    </button>
  </form>
</template>

<style scoped>
.audit-form { display:grid; gap:1rem; margin-bottom:1.25rem; padding:1rem; border:1px solid #dce3e9; border-radius:10px; background:#fff; }
.audit-form h3,.muted { margin:0; }
.muted { color:#667786; }
.audit-form-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:1rem; }
label { display:grid; gap:.4rem; margin:.8rem 0; font-weight:650; }
input,textarea { padding:.65rem; border:1px solid #bac6d0; border-radius:7px; font:inherit; }
.toggle-row { display:flex; align-items:center; gap:.55rem; font-weight:600; }
button { width:max-content; border:0; border-radius:7px; padding:.65rem .9rem; background:#265f8c; color:white; font-weight:700; cursor:pointer; }
button:disabled { opacity:.42; cursor:not-allowed; }
</style>
