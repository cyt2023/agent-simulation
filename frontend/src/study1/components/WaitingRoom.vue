<script setup>
defineProps({
  message: { type: String, default: 'Please wait for the researcher to advance the study.' },
  remainingSeconds: { type: Number, default: null },
  connectionStatus: { type: String, default: 'connected' },
})
</script>

<template>
  <section class="waiting">
    <div class="pulse" aria-hidden="true" />
    <h2>Please wait</h2>
    <p>{{ message }}</p>
    <p v-if="remainingSeconds !== null">Approximate remaining time: {{ remainingSeconds }} seconds</p>
    <p class="connection">Network: {{ connectionStatus }}</p>
  </section>
</template>

<style scoped>
.waiting { text-align:center; padding:3rem 1rem; color:#344455; }
.pulse { width:18px; height:18px; border-radius:50%; background:#3f78a8; margin:0 auto 1rem; box-shadow:0 0 0 9px #dcebf7; }
.connection { color:#687684; font-size:.9rem; }
</style>
