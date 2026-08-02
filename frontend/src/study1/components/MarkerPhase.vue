<script setup>
import PostSessionMarkers from './PostSessionMarkers.vue'

defineProps({
  sessionId: { type: String, required: true },
  fetchMarkers: { type: Function, default: undefined },
  createMarker: { type: Function, default: undefined },
})
</script>

<template>
  <PostSessionMarkers
    :session-id="sessionId"
    :fetch-markers="fetchMarkers"
    :create-marker="createMarker"
    initial-open
  />
</template>
