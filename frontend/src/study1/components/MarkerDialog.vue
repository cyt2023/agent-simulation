<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'submit'])

const markerType = ref('confusing')
const startSeconds = ref(0)
const endSeconds = ref(0)
const reason = ref('')

const markerTypes = [
  { value: 'confusing', label: 'Confusing' },
  { value: 'unexpected', label: 'Unexpected' },
  { value: 'uncomfortable', label: 'Uncomfortable' },
  { value: 'key_decision', label: 'Key decision' },
]

const canSubmit = computed(() => (
  !props.busy
  && markerType.value
  && reason.value.trim()
  && Number(startSeconds.value) >= 0
  && Number(endSeconds.value) >= Number(startSeconds.value)
))

function reset() {
  markerType.value = 'confusing'
  startSeconds.value = 0
  endSeconds.value = 0
  reason.value = ''
}

function submit() {
  if (!canSubmit.value) return
  emit('submit', {
    type: markerType.value,
    start_ms: Math.round(Number(startSeconds.value) * 1000),
    end_ms: Math.round(Number(endSeconds.value) * 1000),
    reason: reason.value.trim(),
  })
}

watch(() => props.open, value => {
  if (value) reset()
})

defineExpose({ reset })
</script>

<template>
  <section v-if="open" class="marker-dialog" aria-label="Post-session marker form">
    <div class="marker-grid">
      <label>
        Marker type
        <select v-model="markerType" data-test="marker-type">
          <option v-for="type in markerTypes" :key="type.value" :value="type.value">
            {{ type.label }}
          </option>
        </select>
      </label>
      <label>
        Start second
        <input v-model.number="startSeconds" data-test="marker-start" type="number" min="0">
      </label>
      <label>
        End second
        <input v-model.number="endSeconds" data-test="marker-end" type="number" min="0">
      </label>
    </div>
    <label>
      Reason
      <textarea v-model="reason" data-test="marker-reason" rows="3" />
    </label>
    <div class="dialog-actions">
      <button type="button" data-test="submit-marker" :disabled="!canSubmit" @click="submit">
        Save marker
      </button>
      <button type="button" class="secondary" @click="emit('close')">
        Cancel
      </button>
    </div>
  </section>
</template>

<style scoped>
.marker-dialog { display:grid; gap:1rem; padding:1rem; border:1px solid #dce3e9; border-radius:9px; background:#fff; }
label { display:grid; gap:.45rem; font-weight:650; }
input,textarea,select { padding:.7rem; border:1px solid #bbc6d1; border-radius:7px; font:inherit; }
.marker-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:.85rem; }
.dialog-actions { display:flex; flex-wrap:wrap; gap:.65rem; }
button { width:max-content; border:0; border-radius:8px; background:#245f8e; color:white; padding:.7rem 1rem; font:inherit; font-weight:700; cursor:pointer; }
button:disabled { opacity:.5; cursor:not-allowed; }
.secondary { background:#edf2f5; color:#2d3d4a; }
</style>
