<script setup>
import { computed, ref } from 'vue'

defineProps({
  busy: { type: Boolean, default: false },
  sessionId: { type: String, required: true },
  role: { type: String, required: true },
})

const emit = defineEmits(['submit'])
const reason = ref('')
const confirmed = ref(false)
const complete = computed(() => reason.value.trim().length >= 8 && confirmed.value)

function submit() {
  emit('submit', {
    request_type: 'withdrawal',
    reason: reason.value.trim(),
    confirmation: confirmed.value,
  })
}
</script>

<template>
  <section class="withdrawal-card">
    <h2>Withdrawal and data retention request</h2>
    <p>
      You may ask the study team to review withdrawal or retention options for this
      Study 1 session. The request creates a controlled privacy workflow; it does
      not silently erase research records.
    </p>
    <label>
      Reason for the request
      <textarea
        v-model="reason"
        data-test="withdrawal-reason"
        rows="4"
        placeholder="Briefly describe the request."
      />
    </label>
    <label class="confirm">
      <input v-model="confirmed" data-test="confirm-withdrawal" type="checkbox">
      I understand the research team will review this request under the approved protocol.
    </label>
    <button
      data-test="submit-withdrawal"
      :disabled="busy || !complete"
      @click="submit"
    >
      Submit request
    </button>
  </section>
</template>

<style scoped>
.withdrawal-card {
  border: 1px solid #dce3e9;
  border-radius: 10px;
  margin-top: 1rem;
  padding: 1rem;
  background: #ffffff;
}

.withdrawal-card p {
  color: #53616d;
  line-height: 1.55;
}

label {
  display: grid;
  gap: .45rem;
  margin-top: .85rem;
  color: #263746;
  font-weight: 700;
}

textarea {
  border: 1px solid #cfd9e1;
  border-radius: 8px;
  padding: .7rem;
  font: inherit;
  resize: vertical;
}

.confirm {
  display: flex;
  align-items: flex-start;
  gap: .55rem;
  font-weight: 500;
}

button {
  border: 0;
  border-radius: 8px;
  margin-top: 1rem;
  padding: .7rem 1rem;
  background: #245f8e;
  color: white;
  font: inherit;
  font-weight: 700;
}

button:disabled {
  opacity: .55;
  cursor: not-allowed;
}
</style>
