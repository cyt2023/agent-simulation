<script setup>
defineProps({
  dashboard: { type: Object, default: null },
})

function valueOrUnknown(value) {
  if (value === true) return 'true'
  if (value === false) return 'false'
  return value || 'unknown'
}
</script>

<template>
  <section class="panel integrity-panel">
    <h2>Protocol integrity</h2>
    <dl class="integrity-grid">
      <div>
        <dt>Protocol version</dt>
        <dd>{{ valueOrUnknown(dashboard?.protocol?.protocol_version || dashboard?.protocol_version) }}</dd>
      </div>
      <div>
        <dt>Protocol checksum</dt>
        <dd>{{ valueOrUnknown(dashboard?.protocol?.checksum || dashboard?.protocol_checksum) }}</dd>
      </div>
      <div>
        <dt>Recording mode</dt>
        <dd>{{ valueOrUnknown(dashboard?.protocol?.recording_mode || dashboard?.recording_mode) }}</dd>
      </div>
      <div>
        <dt>Release</dt>
        <dd>{{ valueOrUnknown(dashboard?.release?.release_id || dashboard?.release_id) }}</dd>
      </div>
      <div>
        <dt>Release checksum</dt>
        <dd>{{ valueOrUnknown(dashboard?.release?.checksum || dashboard?.release_checksum) }}</dd>
      </div>
      <div>
        <dt>ReSync enabled</dt>
        <dd>{{ valueOrUnknown(dashboard?.protocol?.feature_flags?.resync_enabled) }}</dd>
      </div>
      <div>
        <dt>Video enabled</dt>
        <dd>{{ valueOrUnknown(dashboard?.protocol?.feature_flags?.video_enabled) }}</dd>
      </div>
      <div>
        <dt>Integrity status</dt>
        <dd>{{ valueOrUnknown(dashboard?.integrity_report?.status) }}</dd>
      </div>
    </dl>

    <section class="integrity-list">
      <h3>Warnings</h3>
      <p v-if="!(dashboard?.integrity_report?.warnings || []).length">No warnings reported.</p>
      <ul v-else>
        <li v-for="warning in dashboard.integrity_report.warnings" :key="warning">{{ warning }}</li>
      </ul>
    </section>
    <section class="integrity-list">
      <h3>Errors</h3>
      <p v-if="!(dashboard?.integrity_report?.errors || []).length">No errors reported.</p>
      <ul v-else>
        <li v-for="error in dashboard.integrity_report.errors" :key="error">{{ error }}</li>
      </ul>
    </section>
  </section>
</template>

<style scoped>
.panel { background:#f9fbfc; border:1px solid #dce3e9; border-radius:12px; padding:1.25rem; margin:1.25rem 0; }
.integrity-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:1rem; }
.integrity-grid div { min-width:0; border-left:3px solid #cad5dc; padding-left:.75rem; }
dt { color:#667786; font-size:.75rem; font-weight:700; text-transform:uppercase; }
dd { margin:.25rem 0 0; font-weight:700; overflow-wrap:anywhere; }
.integrity-list { margin-top:1rem; }
.integrity-list h3,.integrity-list p { margin:.35rem 0; }
ul { margin:.35rem 0 0; padding-left:1.15rem; }
</style>
