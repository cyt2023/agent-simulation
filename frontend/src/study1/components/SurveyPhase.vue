<script setup>
import { computed, reactive } from 'vue'
const props = defineProps({
  title: { type: String, default: 'Questionnaire' },
  instrument: { type: String, required: true },
  busy: Boolean,
})
const emit = defineEmits(['submit'])
const definitions = {
  delegation_expectation: [
    ['expected_information_shared', 'What information do you expect X to share?', 'textarea'],
    ['expected_recommendation', 'What recommendation do you expect X to make?', 'textarea'],
    ['expected_tentative_agreement', 'What, if anything, may X tentatively agree to?', 'textarea'],
    ['confidence', 'Confidence in these expectations (1-7)', 'scale'],
  ],
  comprehension_measurement: [
    ['conclusion', 'What conclusion did the delegated discussion reach?', 'textarea'],
    ['reasons', 'What reasons support that conclusion?', 'textarea'],
    ['member_positions', 'Describe T1, T2, and X positions separately.', 'textarea'],
    ['disagreements', 'What disagreements or unresolved issues remain?', 'textarea'],
    ['decision_status', 'Is the result a suggestion, tentative consensus, or final commitment?', 'textarea'],
    ['proxy_commitments', 'What commitments, if any, did X make?', 'textarea'],
    ['acceptance_intention', 'What do you intend to accept, reject, or revise?', 'textarea'],
    ['confidence', 'Confidence in your understanding (1-7)', 'scale'],
  ],
  followup_task: [
    ['resource_allocation', 'Allocate the available resources.', 'textarea'],
    ['action_ranking', 'Rank the proposed actions.', 'textarea'],
    ['implementation_plan', 'Provide a short implementation plan.', 'textarea'],
  ],
  post_survey: [
    ['understanding', 'I understood what happened while I was absent (1-7).', 'scale'],
    ['proxy_trust', 'I trust the proxy representation (1-7).', 'scale'],
    ['team_synchronization', 'The team reached shared understanding (1-7).', 'scale'],
    ['comments', 'Comments (enter "none" if there are no comments).', 'textarea'],
  ],
}
const fields = computed(() => definitions[props.instrument] || [])
const answers = reactive({})
for (const group of Object.values(definitions)) {
  for (const [key,, kind] of group) answers[key] = kind === 'scale' ? 4 : ''
}
const complete = computed(() => fields.value.every(([key]) => (
  answers[key] !== '' && answers[key] !== null && answers[key] !== undefined
)))
function submit() {
  if (!complete.value) return
  emit('submit', Object.fromEntries(fields.value.map(([key]) => [key, answers[key]])))
}
</script>

<template>
  <section>
    <h2>{{ title }}</h2>
    <label v-for="[key, label, kind] in fields" :key="key">
      {{ label }}
      <textarea v-if="kind === 'textarea'" v-model="answers[key]" rows="3" />
      <template v-else>
        <input v-model.number="answers[key]" type="range" min="1" max="7">
        <output>{{ answers[key] }}</output>
      </template>
    </label>
    <button :disabled="busy || !complete" @click="submit">
      Submit and lock
    </button>
  </section>
</template>

<style scoped>
label { display:grid; gap:.5rem; margin:1rem 0; font-weight:650; }
textarea { padding:.7rem; border:1px solid #bbc6d1; border-radius:7px; font:inherit; }
output { color:#245f8e; font-weight:800; }
</style>
