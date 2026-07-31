<script setup>
import { computed } from 'vue'
import { displayMicrophoneLabel } from '../services/uiLabels.js'

const props = defineProps({
  mediaStatus: { type: Object, default: null },
  qualitySnapshot: { type: Object, default: null },
})

const componentNames = ['recorder', 'asr', 'llm', 'tts', 'proxy']
const rtc = computed(() => props.qualitySnapshot?.rtc || {})

function titleCase(value) {
  const normalized = String(value || 'unknown').replaceAll('_', ' ').trim() || 'unknown'
  return normalized.charAt(0).toUpperCase() + normalized.slice(1)
}

function componentStatus(name) {
  return props.qualitySnapshot?.components?.[name]
    || props.mediaStatus?.components?.[name]
    || { status: 'unknown' }
}
</script>

<template>
  <section class="panel media-operations">
    <div class="panel-heading">
      <div>
        <h2>Meeting and Proxy service</h2>
        <p>{{ mediaStatus?.service_status || 'checking' }}</p>
      </div>
      <span class="service-state" :data-state="mediaStatus?.service_status">
        {{ mediaStatus?.runtime_state || 'IDLE' }}
      </span>
    </div>

    <dl class="media-grid">
      <div>
        <dt>Room</dt>
        <dd>{{ mediaStatus?.room_kind || 'none' }}<small>{{ mediaStatus?.room_name || 'none' }}</small></dd>
      </div>
      <div>
        <dt>RTC</dt>
        <dd>{{ titleCase(rtc.status) }}<small>Fresh {{ rtc.fresh_participant_count ?? 0 }}, stale {{ rtc.stale_participant_count ?? 0 }}</small></dd>
      </div>
      <div>
        <dt>p50 RTT</dt>
        <dd>{{ rtc.p50_rtt_ms ?? 'unknown' }}<small>ms</small></dd>
      </div>
      <div>
        <dt>p95 RTT</dt>
        <dd>{{ rtc.p95_rtt_ms ?? 'unknown' }}<small>p95 RTT {{ rtc.p95_rtt_ms ?? 'unknown' }} ms</small></dd>
      </div>
    </dl>

    <ul class="component-list">
      <li v-for="component in componentNames" :key="component">
        <strong>{{ component }}</strong>
        <span>{{ titleCase(componentStatus(component).status) }}</span>
        <small>{{ componentStatus(component).last_error_code || 'No error reported' }}</small>
      </li>
    </ul>

    <table v-if="mediaStatus?.connections?.length">
      <thead><tr><th>Media participant</th><th>Role</th><th>Connection</th><th>Microphone</th></tr></thead>
      <tbody>
        <tr v-for="(connection, index) in mediaStatus.connections" :key="connection.participant_id">
          <td>{{ connection.participant_id }}</td>
          <td>{{ connection.role }}</td>
          <td>{{ connection.state }}</td>
          <td>{{ displayMicrophoneLabel(connection.device?.label, index) }}</td>
        </tr>
      </tbody>
    </table>

    <p class="pending">{{ mediaStatus?.pending_callback_count || 0 }} callbacks pending</p>
    <p v-if="mediaStatus?.error" class="error">{{ mediaStatus.error }}</p>
  </section>
</template>

<style scoped>
.panel { background:#f9fbfc; border:1px solid #dce3e9; border-radius:12px; padding:1.25rem; margin:1.25rem 0; }
.panel-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; }
.panel-heading h2,.panel-heading p { margin:0; }
.panel-heading p { margin-top:.25rem; color:#667786; text-transform:capitalize; }
.service-state { padding:.35rem .55rem; border:1px solid #c6d0d8; border-radius:6px; color:#536471; font-size:.78rem; }
.service-state[data-state="ok"] { border-color:#70a883; background:#edf8f1; color:#17633c; }
.media-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1rem; margin:1.25rem 0; }
.media-grid div { min-width:0; border-left:3px solid #cad5dc; padding-left:.75rem; }
.media-grid dt { color:#667786; font-size:.75rem; font-weight:700; text-transform:uppercase; }
.media-grid dd { margin:.25rem 0 0; font-weight:700; overflow-wrap:anywhere; }
.media-grid small { display:block; margin-top:.2rem; color:#70808c; font-weight:400; }
.component-list { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:.65rem; margin:0 0 1rem; padding:0; list-style:none; }
.component-list li { display:grid; gap:.2rem; padding:.75rem; border:1px solid #dce3e9; border-radius:8px; background:#fff; }
.component-list strong { text-transform:capitalize; }
.component-list span { color:#263746; font-weight:700; }
.component-list small,.pending { color:#667786; }
table { width:100%; border-collapse:collapse; }
th,td { text-align:left; border-bottom:1px solid #dde4ea; padding:.65rem; }
.error { background:#fff0f0; color:#922; padding:.75rem; border-radius:7px; }
@media (max-width:720px) {
  .media-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
</style>
