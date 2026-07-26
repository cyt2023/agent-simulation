<script setup>
defineProps({ materials: { type: Array, default: () => [] }, busy: Boolean })
const emit = defineEmits(['acknowledge'])
</script>

<template>
  <section>
    <h2>Your assigned material</h2>
    <p class="neutral">Only the information assigned to your study role is shown here.</p>
    <article v-for="material in materials" :key="material.material_id" class="material">
      <h3>{{ material.title }}</h3>
      <p v-if="material.content" class="content">{{ material.content }}</p>
      <a v-else-if="material.storage_uri" :href="material.storage_uri" target="_blank" rel="noopener">
        Open assigned document
      </a>
    </article>
    <p v-if="!materials.length">No material has been assigned yet.</p>
    <button :disabled="busy || !materials.length" @click="emit('acknowledge')">
      I have finished reading
    </button>
  </section>
</template>

<style scoped>
.neutral { color:#5c6976; }
.material { border:1px solid #dde4eb; border-radius:10px; padding:1rem; margin:1rem 0; background:#fff; }
.content { white-space:pre-wrap; line-height:1.65; }
</style>
