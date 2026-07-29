<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  role: { type: String, required: true },
  consentVersion: { type: String, default: 'study1-consent-v1' },
  busy: Boolean,
  locked: Boolean,
})
const emit = defineEmits(['submit'])
const identityConfirmed = ref(false)
const roleConfirmed = ref(false)
const recordingConfirmed = ref(false)
const voluntaryConfirmed = ref(false)
const complete = computed(() => (
  identityConfirmed.value
  && roleConfirmed.value
  && recordingConfirmed.value
  && voluntaryConfirmed.value
))

function submit() {
  if (!complete.value || props.locked) return
  emit('submit', {
    consent_version: props.consentVersion,
    identity_confirmed: identityConfirmed.value,
    role_confirmed: roleConfirmed.value,
    audio_recording_confirmed: recordingConfirmed.value,
    voluntary_participation_confirmed: voluntaryConfirmed.value,
  })
}
</script>

<template>
  <section class="consent">
    <h2>Consent and identity confirmation</h2>
    <p>
      Confirm your assigned role and consent before the researcher can start.
      Consent version: <code>{{ consentVersion }}</code>
    </p>
    <div v-if="locked" class="locked">
      Consent saved and locked for role <strong>{{ role }}</strong>.
    </div>
    <template v-else>
      <label><input v-model="identityConfirmed" type="checkbox">I confirm that this invitation was issued to me.</label>
      <label><input v-model="roleConfirmed" type="checkbox">I confirm my assigned role is <strong>{{ role }}</strong>.</label>
      <label><input v-model="recordingConfirmed" type="checkbox">I consent to audio recording, transcription, and research data export.</label>
      <label><input v-model="voluntaryConfirmed" type="checkbox">I understand participation is voluntary and I may withdraw.</label>
      <button :disabled="busy || !complete" @click="submit">Save consent and lock</button>
    </template>
  </section>
</template>

<style scoped>
.consent { margin-bottom:1.5rem; padding-bottom:1.5rem; border-bottom:1px solid #dce3e9; }
label { display:flex; align-items:flex-start; gap:.65rem; margin:.85rem 0; line-height:1.45; }
input { margin-top:.25rem; }
.locked { padding:.85rem 1rem; border-radius:8px; background:#e9f7ef; color:#17633c; }
</style>
