<script setup>
import { ref } from 'vue'
import { Upload } from '@lucide/vue'

import { fileSelectionLabel } from '../services/uiLabels.js'

defineProps({
  inputId: { type: String, required: true },
})

const emit = defineEmits(['files-change'])
const selectedFiles = ref([])

function selectFiles(event) {
  selectedFiles.value = Array.from(event.target.files || [])
  emit('files-change', selectedFiles.value)
}
</script>

<template>
  <div class="file-picker">
    <input
      :id="inputId"
      class="sr-only"
      type="file"
      accept=".pdf,.txt,.md"
      multiple
      @change="selectFiles"
    >
    <label class="file-button" :for="inputId">
      <Upload :size="17" aria-hidden="true" />
      Choose files
    </label>
    <span class="file-status" aria-live="polite">
      {{ fileSelectionLabel(selectedFiles) }}
    </span>
  </div>
</template>

<style scoped>
.file-picker { display:flex; align-items:center; flex-wrap:wrap; gap:.65rem; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
.file-button { display:inline-flex; align-items:center; gap:.45rem; padding:.6rem .75rem; border:1px solid #aebbc5; border-radius:7px; background:#fff; color:#334754; font-weight:700; cursor:pointer; }
.sr-only:focus-visible + .file-button { outline:3px solid rgba(38,95,140,.3); outline-offset:2px; }
.file-status { color:#667482; font-size:.9rem; font-weight:500; }
</style>
