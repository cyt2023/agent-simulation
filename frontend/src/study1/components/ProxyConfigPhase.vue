<script setup>
import { ref } from 'vue'

defineProps({
  role: { type: String, required: true },
  busy: Boolean,
  materials: { type: Array, default: () => [] },
})
const emit = defineEmits(['submit'])
const priorities = ref('')
const boundaries = ref('')
const authorizedMaterialIds = ref([])
const authorizationConfirmed = ref(false)

function submitProxyConfig() {
  emit('submit', {
    priorities: priorities.value.trim(),
    boundaries: boundaries.value.trim(),
    authorization_confirmed: authorizationConfirmed.value,
    authorized_material_ids: [...authorizedMaterialIds.value],
  })
}
</script>

<template>
  <section>
    <template v-if="role === 'principal'">
      <h2>Configure your proxy</h2>
      <label>Priorities<textarea v-model="priorities" data-test="proxy-priorities" rows="4" /></label>
      <label>Boundaries<textarea v-model="boundaries" rows="4" /></label>
      <fieldset>
        <legend>Materials shared with X</legend>
        <label v-for="material in materials" :key="material.material_id" class="material-option">
          <input
            v-model="authorizedMaterialIds"
            type="checkbox"
            :value="material.material_id"
            :data-test="`material-${material.material_id}`"
          >
          <span>{{ material.title || 'Untitled material' }}</span>
        </label>
        <p v-if="!materials.length" class="muted">No P materials are available to authorize.</p>
      </fieldset>
      <label class="confirmation">
        <input
          v-model="authorizationConfirmed"
          data-test="authorization-confirmed"
          type="checkbox"
        >
        <span>I authorize X to use only the selected materials and the configuration above.</span>
      </label>
      <button
        data-test="submit-proxy-config"
        :disabled="busy || !priorities.trim() || !authorizationConfirmed"
        @click="submitProxyConfig"
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
fieldset { display:grid; gap:.55rem; margin:1rem 0; padding:1rem; border:1px solid #bbc6d1; border-radius:7px; }
legend { padding:0 .35rem; font-weight:700; }
.material-option,.confirmation { display:flex; align-items:flex-start; gap:.55rem; margin:0; font-weight:500; }
.material-option input,.confirmation input { margin-top:.2rem; }
.muted { margin:0; color:#667482; }
</style>
