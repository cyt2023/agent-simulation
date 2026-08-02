<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  title: { type: String, default: 'Submit your judgment' },
  prompt: { type: String, default: 'Enter your decision and explanation.' },
  variant: { type: String, default: 'pre' },
  candidates: { type: Array, default: () => [] },
  busy: Boolean,
  locked: Boolean,
  available: { type: Boolean, default: true },
  unavailableMessage: {
    type: String,
    default: 'This action is not available in the current server state.',
  },
})
const emit = defineEmits(['submit'])
const candidateId = ref('')
const rationale = ref('')
const confidence = ref(4)
const decisionStatus = ref('')
const proxyAuthorityBelief = ref('')
const expectedPrincipalAcceptance = ref(4)

const candidateOptions = computed(() => props.candidates.map(normalizeCandidate))

watch(candidateOptions, (options) => {
  if (!candidateId.value && options.length === 1) candidateId.value = options[0].id
  if (candidateId.value && !options.some(option => option.id === candidateId.value)) {
    candidateId.value = ''
  }
}, { immediate: true })

const isComplete = () => (
  candidateId.value
  && rationale.value.trim()
  && (!props.variant.includes('tentative') || (decisionStatus.value && proxyAuthorityBelief.value))
)

function submit() {
  if (!props.available || props.locked || !isComplete()) return
  const payload = {
    candidate_id: candidateId.value,
    rationale: rationale.value.trim(),
    confidence: Number(confidence.value),
  }
  if (props.variant.includes('tentative')) {
    Object.assign(payload, {
      decision_status: decisionStatus.value,
      proxy_authority_belief: proxyAuthorityBelief.value,
      expected_principal_acceptance: Number(expectedPrincipalAcceptance.value),
    })
  }
  emit('submit', payload)
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
</script>

<template>
  <section>
    <h2>{{ title }}</h2>
    <p>{{ prompt }}</p>
    <p v-if="locked" class="locked">Your response is saved and locked.</p>
    <p v-else-if="!available" class="unavailable">{{ unavailableMessage }}</p>
    <fieldset v-else class="candidate-group">
      <legend>Decision</legend>
      <label v-for="candidate in candidateOptions" :key="candidate.id" class="candidate-option">
        <input v-model="candidateId" type="radio" :value="candidate.id">
        <span>{{ candidate.label }}</span>
      </label>
      <p v-if="!candidateOptions.length" class="muted">No registered candidates are available yet.</p>
    </fieldset>
    <label>Explanation<textarea v-model="rationale" rows="5" :disabled="locked || !available" /></label>
    <label>Confidence (1 = very low, 7 = very high)
      <input v-model.number="confidence" type="range" min="1" max="7" :disabled="locked || !available" />
      <output>{{ confidence }}</output>
    </label>
    <template v-if="variant.includes('tentative')">
      <label>Current decision status
        <select v-model="decisionStatus" :disabled="locked || !available">
          <option value="">Select...</option>
          <option value="open">Open</option>
          <option value="tentative">Tentative</option>
          <option value="settled">Settled</option>
        </select>
      </label>
      <label>Did X have authority to agree on P's behalf?
        <select v-model="proxyAuthorityBelief" :disabled="locked || !available">
          <option value="">Select...</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
          <option value="uncertain">Uncertain</option>
        </select>
      </label>
      <label>Expected P acceptance (1-7)
        <input v-model.number="expectedPrincipalAcceptance" type="range" min="1" max="7" :disabled="locked || !available" />
        <output>{{ expectedPrincipalAcceptance }}</output>
      </label>
    </template>
    <button :disabled="busy || locked || !available || !isComplete()" @click="submit">Submit and lock</button>
  </section>
</template>

<style scoped>
label { display:grid; gap:.4rem; margin:1rem 0; font-weight:650; }
input,textarea,select { padding:.7rem; border:1px solid #bbc6d1; border-radius:7px; font:inherit; }
input[type="range"], input[type="radio"] { padding:0; }
output { color:#245f8e; font-weight:800; }
.candidate-group { display:grid; gap:.55rem; margin:1rem 0; padding:1rem; border:1px solid #bbc6d1; border-radius:8px; }
.candidate-option { display:flex; align-items:center; gap:.55rem; margin:0; font-weight:650; }
.locked { padding:.75rem .9rem; border-radius:8px; background:#e9f7ef; color:#17633c; }
.unavailable { padding:.75rem .9rem; border-radius:8px; background:#f1f4f6; color:#5d6b75; }
.muted { margin:0; color:#667482; }
</style>
