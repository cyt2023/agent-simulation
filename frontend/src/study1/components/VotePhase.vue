<script setup>
import { ref } from 'vue'

defineProps({
  title: { type: String, default: 'Submit your judgment' },
  prompt: { type: String, default: 'Enter your decision and explanation.' },
  busy: Boolean,
})
const emit = defineEmits(['submit'])
const decision = ref('')
const rationale = ref('')
function submit() {
  if (!decision.value.trim()) return
  emit('submit', { decision: decision.value.trim(), rationale: rationale.value.trim() })
}
</script>

<template>
  <section>
    <h2>{{ title }}</h2>
    <p>{{ prompt }}</p>
    <label>Decision<input v-model="decision" autocomplete="off" /></label>
    <label>Explanation<textarea v-model="rationale" rows="5" /></label>
    <button :disabled="busy || !decision.trim()" @click="submit">Submit and lock</button>
  </section>
</template>

<style scoped>
label { display:grid; gap:.4rem; margin:1rem 0; font-weight:650; }
input,textarea { padding:.7rem; border:1px solid #bbc6d1; border-radius:7px; font:inherit; }
</style>
