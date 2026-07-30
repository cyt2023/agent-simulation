<script setup>
defineProps({
  eyebrow: { type: String, default: 'Current task' },
  title: { type: String, default: 'Follow the current study step' },
  description: { type: String, default: '' },
})
</script>

<template>
  <aside class="task-panel" aria-labelledby="study-task-title">
    <span class="eyebrow">{{ eyebrow }}</span>
    <h2 id="study-task-title">{{ title }}</h2>
    <p v-if="description">{{ description }}</p>
    <div class="task-content"><slot /></div>
  </aside>
</template>

<style scoped>
.task-panel { min-width:0; padding:1.25rem; border-left:1px solid #d8dfe4; background:#f5f7f7; }
.eyebrow { color:#60717c; font-size:.72rem; font-weight:800; text-transform:uppercase; }
h2 { margin:.35rem 0 .5rem; font-size:1.08rem; color:#1f303a; }
p { margin:0 0 1rem; color:#65747e; font-size:.86rem; line-height:1.5; }
.task-content { min-width:0; }
@media (max-width:860px) { .task-panel { border-left:0; border-top:1px solid #d8dfe4; } }
</style>
