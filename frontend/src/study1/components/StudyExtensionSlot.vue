<script setup>
import { shallowRef, watch } from 'vue'

import { loadStudyExtension } from '../extensions/registry.js'

const props = defineProps({
  enabled: { type: Boolean, default: false },
  moduleId: { type: String, default: '' },
})

const extension = shallowRef(null)

watch(
  () => [props.enabled, props.moduleId],
  async ([enabled, moduleId]) => {
    extension.value = null
    if (!enabled) return
    extension.value = await loadStudyExtension(moduleId)
  },
  { immediate: true },
)
</script>

<template>
  <component :is="extension" v-if="extension" />
</template>
