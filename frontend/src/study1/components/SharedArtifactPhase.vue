<script setup>
import { computed, reactive, watch } from 'vue'

const props = defineProps({
  title: { type: String, default: 'Shared team artifact' },
  kind: { type: String, required: true },
  role: { type: String, required: true },
  candidates: { type: Array, default: () => [] },
  artifact: { type: Object, default: null },
  busy: Boolean,
  canEdit: { type: Boolean, default: true },
  canConfirm: { type: Boolean, default: true },
})
const emit = defineEmits(['edit', 'confirm'])

const form = reactive({
  candidate_id: '',
  rationale: '',
  confidence: 4,
  decision_status: 'tentative',
  resource_allocation_text: '',
  ranked_actions_text: '',
  implementation_plan: '',
})

const currentRevision = computed(() => props.artifact?.current_revision || null)
const confirmedRoles = computed(() => currentRevision.value?.confirmed_roles || [])
const locked = computed(() => Boolean(props.artifact?.locked || currentRevision.value?.locked))
const isTeamFinal = computed(() => props.kind === 'team_final')
const candidateOptions = computed(() => props.candidates.map(normalizeCandidate))
const confirmationText = computed(() => `${confirmedRoles.value.length} of 3 confirmed`)
const alreadyConfirmed = computed(() => confirmedRoles.value.includes(props.role))
const canConfirmRevision = computed(() => (
  props.canConfirm
  && Boolean(currentRevision.value?.revision_id)
  && !locked.value
  && !alreadyConfirmed.value
))
const canSave = computed(() => {
  if (locked.value || !props.canEdit) return false
  if (isTeamFinal.value) return Boolean(form.candidate_id && form.rationale.trim())
  return Boolean(form.resource_allocation_text.trim() && form.ranked_actions_text.trim() && form.implementation_plan.trim())
})

watch(currentRevision, (revision) => {
  const content = revision?.content || {}
  form.candidate_id = content.candidate_id || ''
  form.rationale = content.rationale || ''
  form.confidence = Number(content.confidence || 4)
  form.decision_status = content.decision_status || 'tentative'
  form.resource_allocation_text = (content.resource_allocation || [])
    .map(item => `${item.resource || ''}: ${item.allocation || ''}`.trim())
    .filter(Boolean)
    .join('\n')
  form.ranked_actions_text = (content.ranked_actions || []).join('\n')
  form.implementation_plan = content.implementation_plan || ''
}, { immediate: true })

watch(candidateOptions, (options) => {
  if (!form.candidate_id && options.length === 1) form.candidate_id = options[0].id
  if (form.candidate_id && options.length && !options.some(option => option.id === form.candidate_id)) {
    form.candidate_id = ''
  }
}, { immediate: true })

function edit(contentOverride = null) {
  if (!props.canEdit) return
  const content = contentOverride || buildContent()
  emit('edit', {
    parent_revision_id: currentRevision.value?.revision_id || null,
    content,
  })
}

function confirm() {
  if (!props.canConfirm || !currentRevision.value?.revision_id) return
  emit('confirm', currentRevision.value.revision_id)
}

function buildContent() {
  if (!isTeamFinal.value) {
    return {
      resource_allocation: parseResourceAllocation(form.resource_allocation_text),
      ranked_actions: parseLines(form.ranked_actions_text),
      implementation_plan: form.implementation_plan.trim(),
    }
  }
  return {
    candidate_id: form.candidate_id,
    rationale: form.rationale.trim(),
    confidence: Number(form.confidence),
    decision_status: form.decision_status,
    ratings: {},
  }
}

function parseLines(value) {
  return String(value || '').split(/\r?\n/).map(line => line.trim()).filter(Boolean)
}

function parseResourceAllocation(value) {
  return parseLines(value).map(line => {
    const [resource, ...rest] = line.split(':')
    return {
      resource: resource.trim(),
      allocation: rest.join(':').trim() || 'Allocated',
    }
  })
}

function normalizeCandidate(value) {
  if (value && typeof value === 'object') {
    const id = String(value.candidate_id || value.id || '').trim()
    return { id, label: value.label || candidateLabel(id) }
  }
  const id = String(value || '').trim()
  return { id, label: candidateLabel(id) }
}

function candidateLabel(id) {
  const cleaned = String(id || '').trim()
  const suffix = cleaned.replace(/^candidate[-_]?/i, '')
  if (suffix && /^[a-z0-9]+$/i.test(suffix)) return `Candidate ${suffix.toUpperCase()}`
  return cleaned || 'Unnamed candidate'
}

function roleLabel(role) {
  return {
    principal: 'P',
    teammate_1: 'T1',
    teammate_2: 'T2',
  }[role] || role
}
</script>

<template>
  <section class="shared-artifact">
    <header>
      <div>
        <h2>{{ title }}</h2>
        <p>{{ kind.replaceAll('_', ' ') }}</p>
      </div>
      <strong data-test="confirmation-count">{{ confirmationText }}</strong>
    </header>

    <ol class="confirmation-list" aria-label="Confirmation status">
      <li
        v-for="confirmationRole in ['principal', 'teammate_1', 'teammate_2']"
        :key="confirmationRole"
        :data-confirmed="confirmedRoles.includes(confirmationRole)"
      >
        {{ roleLabel(confirmationRole) }}
      </li>
    </ol>

    <p v-if="locked" class="locked">This shared artifact is locked.</p>
    <p v-else-if="!canEdit && !canConfirm" class="unavailable">
      Editing and confirmation are not available in the current server state.
    </p>
    <p v-else-if="!canEdit" class="unavailable">
      Editing is not available in the current server state.
    </p>
    <p v-else-if="!canConfirm" class="unavailable">
      Confirmation is not available in the current server state.
    </p>

    <fieldset :disabled="locked || !canEdit" class="artifact-fields">
      <template v-if="isTeamFinal">
        <fieldset class="candidate-group">
          <legend>Team decision</legend>
          <label v-for="candidate in candidateOptions" :key="candidate.id" class="candidate-option">
            <input v-model="form.candidate_id" type="radio" :value="candidate.id">
            <span>{{ candidate.label }}</span>
          </label>
          <p v-if="!candidateOptions.length" class="muted">No registered candidates are available yet.</p>
        </fieldset>
        <label>
          Shared rationale
          <textarea v-model="form.rationale" data-test="shared-rationale" rows="4" />
        </label>
        <label>
          Team confidence (1-7)
          <input v-model.number="form.confidence" type="range" min="1" max="7">
          <output>{{ form.confidence }}</output>
        </label>
        <label>
          Decision status
          <select v-model="form.decision_status">
            <option value="open">Open</option>
            <option value="tentative">Tentative</option>
            <option value="settled">Settled</option>
          </select>
        </label>
      </template>

      <template v-else>
        <label>
          Resource allocation
          <textarea v-model="form.resource_allocation_text" rows="4" placeholder="Budget: 60% to implementation" />
        </label>
        <label>
          Ranked actions
          <textarea v-model="form.ranked_actions_text" rows="4" placeholder="Validate the plan" />
        </label>
        <label>
          Implementation plan
          <textarea v-model="form.implementation_plan" rows="4" />
        </label>
      </template>
    </fieldset>

    <div class="actions">
      <button
        data-test="save-shared-revision"
        :disabled="busy || !canSave"
        @click="edit()"
      >
        Save new revision
      </button>
      <button
        data-test="confirm-shared-revision"
        :disabled="busy || !canConfirmRevision"
        @click="confirm"
      >
        Confirm current revision
      </button>
    </div>
  </section>
</template>

<style scoped>
.shared-artifact { display:grid; gap:1rem; }
header { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; }
h2,p { margin:0; }
header p { margin-top:.25rem; color:#667482; text-transform:capitalize; }
header strong { padding:.35rem .55rem; border:1px solid #ccd5dd; border-radius:7px; color:#43535f; font-size:.8rem; }
label { display:grid; gap:.45rem; font-weight:650; }
textarea,select,input { padding:.7rem; border:1px solid #bbc6d1; border-radius:7px; font:inherit; }
input[type="range"], input[type="radio"] { padding:0; }
output { color:#245f8e; font-weight:800; }
.candidate-group { display:grid; gap:.55rem; margin:0; padding:1rem; border:1px solid #bbc6d1; border-radius:8px; }
.candidate-option { display:flex; align-items:center; gap:.55rem; margin:0; }
.confirmation-list { display:flex; gap:.45rem; padding:0; margin:0; list-style:none; }
.confirmation-list li { padding:.3rem .5rem; border:1px solid #ccd5dd; border-radius:999px; color:#667482; font-size:.78rem; }
.confirmation-list li[data-confirmed="true"] { border-color:#6aa77e; background:#eef8f1; color:#17633c; }
.actions { display:flex; flex-wrap:wrap; gap:.65rem; }
.locked { padding:.75rem .9rem; border-radius:8px; background:#e9f7ef; color:#17633c; }
.unavailable { padding:.75rem .9rem; border-radius:8px; background:#f1f4f6; color:#5d6b75; }
.artifact-fields { margin:0; padding:0; border:0; }
.muted { color:#667482; }
</style>
