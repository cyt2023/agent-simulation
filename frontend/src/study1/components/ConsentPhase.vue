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
const voluntaryConfirmed = ref(false)
const consentScopes = ref({
  audio_recording: false,
  transcription: false,
  ui_telemetry: false,
  external_agent_processing: false,
})
const scopeLabels = [
  {
    key: 'audio_recording',
    label: 'I consent to audio recording during the Study 1 meetings.',
  },
  {
    key: 'transcription',
    label: 'I consent to speech transcription for research analysis.',
  },
  {
    key: 'ui_telemetry',
    label: 'I consent to interface telemetry such as review reading and scrolling events.',
  },
  {
    key: 'external_agent_processing',
    label: 'I consent to external Agent or provider processing required by the Proxy and Summary pipeline.',
  },
]
const complete = computed(() => (
  identityConfirmed.value
  && roleConfirmed.value
  && Object.values(consentScopes.value).every(Boolean)
  && voluntaryConfirmed.value
))

function submit() {
  if (!complete.value || props.locked) return
  emit('submit', {
    consent_version: props.consentVersion,
    identity_confirmed: identityConfirmed.value,
    role_confirmed: roleConfirmed.value,
    consent_scopes: { ...consentScopes.value },
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
      <label><input v-model="identityConfirmed" data-test="identity-confirmed" type="checkbox">I confirm that this invitation was issued to me.</label>
      <label><input v-model="roleConfirmed" data-test="role-confirmed" type="checkbox">I confirm my assigned role is <strong>{{ role }}</strong>.</label>
      <label v-for="scope in scopeLabels" :key="scope.key">
        <input
          v-model="consentScopes[scope.key]"
          :data-test="`scope-${scope.key}`"
          type="checkbox"
        >
        {{ scope.label }}
      </label>
      <label><input v-model="voluntaryConfirmed" data-test="voluntary-confirmed" type="checkbox">I understand participation is voluntary and I may withdraw.</label>
      <button data-test="submit-consent" :disabled="busy || !complete" @click="submit">Save consent and lock</button>
    </template>
  </section>
</template>

<style scoped>
.consent { margin-bottom:1.5rem; padding-bottom:1.5rem; border-bottom:1px solid #dce3e9; }
label { display:flex; align-items:flex-start; gap:.65rem; margin:.85rem 0; line-height:1.45; }
input { margin-top:.25rem; }
.locked { padding:.85rem 1rem; border-radius:8px; background:#e9f7ef; color:#17633c; }
</style>
