<script setup>
import { ref } from 'vue'

defineProps({ role: { type: String, required: true }, busy: Boolean })
const emit = defineEmits(['submit'])
const priorities = ref('')
const boundaries = ref('')
</script>

<template>
  <section>
    <template v-if="role === 'principal'">
      <h2>Configure your proxy</h2>
      <p>Describe priorities and boundaries. The meeting implementation is external to this system.</p>
      <label>Priorities<textarea v-model="priorities" rows="4" /></label>
      <label>Boundaries<textarea v-model="boundaries" rows="4" /></label>
      <button
        :disabled="busy || !priorities.trim()"
        @click="emit('submit', { priorities: priorities.trim(), boundaries: boundaries.trim() })"
      >
        Submit proxy configuration
      </button>
    </template>
    <template v-else>
      <h2>Confirm readiness</h2>
      <p>The researcher will start the delegated meeting after both teammates are ready.</p>
      <button :disabled="busy" @click="emit('submit', { ready: true })">I am ready</button>
    </template>
  </section>
</template>

<style scoped>
label { display:grid; gap:.4rem; margin:1rem 0; font-weight:650; }
textarea { padding:.7rem; border:1px solid #bbc6d1; border-radius:7px; font:inherit; }
</style>
