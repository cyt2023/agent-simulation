<script setup>
import { computed, reactive, watch } from 'vue'

const props = defineProps({
  title: { type: String, default: 'Questionnaire' },
  instrument: { type: Object, default: null },
  busy: Boolean,
  locked: Boolean,
  available: { type: Boolean, default: true },
  unavailableMessage: {
    type: String,
    default: 'This action is not available in the current server state.',
  },
})
const emit = defineEmits(['submit'])
const answers = reactive({})
const items = computed(() => props.instrument?.items || [])

watch(items, (nextItems) => {
  for (const item of nextItems) {
    if (answers[item.item_id] !== undefined) continue
    answers[item.item_id] = defaultValue(item)
  }
}, { immediate: true })

const complete = computed(() => items.value.every(item => (
  !item.required || (
    answers[item.item_id] !== ''
    && answers[item.item_id] !== null
    && answers[item.item_id] !== undefined
  )
)))

function defaultValue(item) {
  if (item.response_type === 'integer') return Number(item.constraints?.min || 1)
  return ''
}

function enumValues(item) {
  return item.constraints?.values || []
}

function submit() {
  if (!props.instrument || !complete.value || props.locked || !props.available) return
  emit('submit', {
    instrument_definition_id: props.instrument.instrument_definition_id,
    instrument_version: props.instrument.instrument_version,
    ordered_responses: items.value.map(item => ({
      item_id: item.item_id,
      response: answers[item.item_id],
    })),
  })
}
</script>

<template>
  <section>
    <h2>{{ title }}</h2>
    <p v-if="locked" class="locked">Your response is saved and locked.</p>
    <p v-else-if="!available" class="unavailable">{{ unavailableMessage }}</p>
    <p v-if="!instrument" class="muted">No server-defined instrument is available for this step.</p>
    <fieldset :disabled="locked || !available" class="instrument-fields">
      <label
        v-for="item in items"
        :key="item.item_id"
        data-test="instrument-item"
      >
        {{ item.prompt }}
        <textarea
          v-if="item.response_type === 'text'"
          v-model="answers[item.item_id]"
          :data-test="`instrument-${item.item_id}`"
          rows="3"
          :maxlength="item.constraints?.max_length"
        />
        <select
          v-else-if="item.response_type === 'enum'"
          v-model="answers[item.item_id]"
          :data-test="`instrument-${item.item_id}`"
        >
          <option value="">Select...</option>
          <option v-for="value in enumValues(item)" :key="value" :value="value">
            {{ value.replaceAll('_', ' ') }}
          </option>
        </select>
        <template v-else>
          <input
            v-model.number="answers[item.item_id]"
            :data-test="`instrument-${item.item_id}`"
            type="range"
            :min="item.constraints?.min || 1"
            :max="item.constraints?.max || 7"
          >
          <output>{{ answers[item.item_id] }}</output>
        </template>
      </label>
    </fieldset>
    <button
      data-test="submit-instrument"
      :disabled="busy || locked || !available || !instrument || !complete"
      @click="submit"
    >
      Submit and lock
    </button>
  </section>
</template>

<style scoped>
label { display:grid; gap:.5rem; margin:1rem 0; font-weight:650; }
textarea,select,input { padding:.7rem; border:1px solid #bbc6d1; border-radius:7px; font:inherit; }
input[type="range"] { padding:0; }
output { color:#245f8e; font-weight:800; }
.instrument-fields { margin:0; padding:0; border:0; }
.locked { padding:.75rem .9rem; border-radius:8px; background:#e9f7ef; color:#17633c; }
.unavailable { padding:.75rem .9rem; border-radius:8px; background:#f1f4f6; color:#5d6b75; }
.muted { color:#667482; }
</style>
