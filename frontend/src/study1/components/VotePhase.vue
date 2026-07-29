<script setup>
import { ref } from 'vue'

const props = defineProps({
  title: { type: String, default: 'Submit your judgment' },
  prompt: { type: String, default: 'Enter your decision and explanation.' },
  variant: { type: String, default: 'pre' },
  busy: Boolean,
})
const emit = defineEmits(['submit'])
const decision = ref('')
const rationale = ref('')
const confidence = ref(4)
const decisionStatus = ref('')
const proxyAuthorityBelief = ref('')
const expectedPrincipalAcceptance = ref(4)
const decisionScope = ref('')
const isComplete = () => (
  decision.value.trim()
  && rationale.value.trim()
  && (!props.variant.includes('tentative') || (decisionStatus.value && proxyAuthorityBelief.value))
  && (props.variant !== 'final' || decisionScope.value)
)
function submit() {
  if (!isComplete()) return
  const payload = {
    decision: decision.value.trim(),
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
  if (props.variant === 'final') payload.decision_scope = decisionScope.value
  emit('submit', payload)
}
</script>

<template>
  <section>
    <h2>{{ title }}</h2>
    <p>{{ prompt }}</p>
    <label>Decision<input v-model="decision" autocomplete="off" /></label>
    <label>Explanation<textarea v-model="rationale" rows="5" /></label>
    <label>Confidence (1 = very low, 7 = very high)
      <input v-model.number="confidence" type="range" min="1" max="7" />
      <output>{{ confidence }}</output>
    </label>
    <template v-if="variant.includes('tentative')">
      <label>Current decision status
        <select v-model="decisionStatus">
          <option value="">Select…</option>
          <option value="suggestion">Suggestion only</option>
          <option value="tentative_consensus">Tentative consensus</option>
          <option value="final_commitment">Final commitment</option>
        </select>
      </label>
      <label>Did X have authority to agree on P's behalf?
        <select v-model="proxyAuthorityBelief">
          <option value="">Select…</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
          <option value="uncertain">Uncertain</option>
        </select>
      </label>
      <label>Expected P acceptance (1–7)
        <input v-model.number="expectedPrincipalAcceptance" type="range" min="1" max="7" />
        <output>{{ expectedPrincipalAcceptance }}</output>
      </label>
    </template>
    <label v-if="variant === 'final'">Decision scope
      <select v-model="decisionScope">
        <option value="">Select…</option>
        <option value="individual">My individual final decision</option>
        <option value="team">The team's agreed final decision</option>
      </select>
    </label>
    <button :disabled="busy || !isComplete()" @click="submit">Submit and lock</button>
  </section>
</template>

<style scoped>
label { display:grid; gap:.4rem; margin:1rem 0; font-weight:650; }
input,textarea,select { padding:.7rem; border:1px solid #bbc6d1; border-radius:7px; font:inherit; }
input[type="range"] { padding:0; }
output { color:#245f8e; font-weight:800; }
</style>
