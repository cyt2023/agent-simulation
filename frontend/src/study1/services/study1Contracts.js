const DEFAULT_CAPABILITIES = Object.freeze({
  submit_consent: false,
  submit_material_ack: false,
  submit_pre_individual: false,
  configure_proxy: false,
  submit_proxy_ready: false,
  join_proxy_meeting: false,
  submit_tentative_decision: false,
  submit_tentative_individual: false,
  submit_delegation_expectation: false,
  read_review: false,
  submit_comprehension_measurement: false,
  join_sync_meeting: false,
  submit_final_individual: false,
  edit_team_final: false,
  confirm_team_final: false,
  edit_followup_task: false,
  confirm_followup_task: false,
  submit_final_decision: false,
  submit_followup_task: false,
  submit_post_survey: false,
})

const VIDEO_SOURCES = new Set(['camera', 'screen_share', 'screen', 'video'])

export function normalizeParticipantState(value = {}) {
  const capabilities = { ...DEFAULT_CAPABILITIES }
  for (const [key, enabled] of Object.entries(value.capabilities || {})) {
    capabilities[key] = Boolean(enabled)
  }
  return {
    ...value,
    phase: String(value.phase || 'SETUP'),
    phase_version: Number(value.phase_version || 0),
    capabilities,
  }
}

export function normalizeMediaAccess(value = {}) {
  const publishSources = [
    ...(value.publish_sources || []),
    ...(value.publishSources || []),
  ].map(source => String(source || '').toLowerCase()).filter(Boolean)
  if (publishSources.some(source => VIDEO_SOURCES.has(source))) {
    throw new Error('Study 1 media is audio-only; video sources are not allowed.')
  }
  return {
    ...value,
    publish_sources: publishSources.length ? publishSources : ['microphone'],
    captions_enabled: Boolean(value.captions_enabled),
  }
}

export function normalizeResearcherMediaStatus(value = {}) {
  const components = value.components || {}
  return {
    ...value,
    service_status: value.service_status || 'unknown',
    runtime_state: value.runtime_state || 'IDLE',
    components: {
      recorder: normalizeComponent(components.recorder || value.recording),
      asr: normalizeComponent(components.asr || value.asr),
      llm: normalizeComponent(components.llm),
      tts: normalizeComponent(components.tts),
      proxy: normalizeComponent(components.proxy || value.proxy),
    },
    rtc: {
      status: value.rtc?.status || 'unknown',
      p50_rtt_ms: value.rtc?.p50_rtt_ms ?? null,
      p95_rtt_ms: value.rtc?.p95_rtt_ms ?? null,
      participant_count: value.rtc?.participant_count || 0,
    },
  }
}

function normalizeComponent(value = {}) {
  const status = String(value?.status || 'unknown')
  return {
    status: ['unknown', 'healthy', 'degraded', 'failed', 'active', 'complete']
      .includes(status)
      ? status
      : 'unknown',
    last_error_code: value?.last_error_code || null,
    p50_latency_ms: value?.p50_latency_ms ?? null,
    p95_latency_ms: value?.p95_latency_ms ?? null,
  }
}
