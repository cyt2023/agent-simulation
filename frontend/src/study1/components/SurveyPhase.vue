<script setup>
import { ref } from 'vue'
defineProps({ title: { type: String, default: 'Questionnaire' }, busy: Boolean })
const emit = defineEmits(['submit'])
const answer = ref('')
</script>

<template>
  <section>
    <h2>{{ title }}</h2>
    <label>Your response<textarea v-model="answer" rows="7" /></label>
    <button :disabled="busy || !answer.trim()" @click="emit('submit', { response: answer.trim() })">
      Submit and lock
    </button>
  </section>
</template>

<style scoped>
label { display:grid; gap:.5rem; margin:1rem 0; font-weight:650; }
textarea { padding:.7rem; border:1px solid #bbc6d1; border-radius:7px; font:inherit; }
</style>
