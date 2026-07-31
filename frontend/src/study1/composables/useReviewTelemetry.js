import { sendReviewEventBatch as defaultSendBatch } from '../services/study1Api.js'

function nowMs() {
  return Date.now()
}

function createEvent(sequenceNo, eventType, observedAtMs, payload = {}) {
  return {
    sequence_no: sequenceNo,
    event_type: eventType,
    observed_at_ms: observedAtMs,
    payload,
  }
}

export function createReviewTelemetry({
  sessionId,
  visitId = `review-${nowMs()}-${Math.random().toString(36).slice(2)}`,
  sendBatch = defaultSendBatch,
} = {}) {
  let sequenceNo = 0
  let pendingEvents = []
  let activeMs = 0
  let visible = false
  let focused = false
  let lastHeartbeatMs = null

  function applyLocalState(eventType, observedAtMs, payload = {}) {
    if (eventType === 'enter') {
      visible = true
      focused = true
      lastHeartbeatMs = observedAtMs
      return
    }
    if (eventType === 'leave') {
      visible = false
      focused = false
      lastHeartbeatMs = null
      return
    }
    if (eventType === 'visibility') {
      visible = payload.state === 'visible'
      lastHeartbeatMs = visible ? observedAtMs : null
      return
    }
    if (eventType === 'focus') {
      focused = payload.focused !== false
      lastHeartbeatMs = focused ? observedAtMs : null
      return
    }
    if (eventType === 'heartbeat') {
      if (visible && focused && lastHeartbeatMs !== null) {
        const gap = Math.max(0, observedAtMs - lastHeartbeatMs)
        if (gap <= 15_000) activeMs += gap
      }
      lastHeartbeatMs = visible && focused ? observedAtMs : null
    }
  }

  async function record(eventType, payload = {}, observedAtMs = nowMs()) {
    sequenceNo += 1
    const event = createEvent(sequenceNo, eventType, observedAtMs, payload)
    applyLocalState(eventType, observedAtMs, payload)
    const events = [...pendingEvents, event]
    try {
      await sendBatch(sessionId, { visit_id: visitId, events })
      pendingEvents = []
    } catch {
      pendingEvents = events
    }
    return event
  }

  return {
    visitId,
    event: record,
    enter: observedAtMs => record('enter', {}, observedAtMs),
    leave: observedAtMs => record('leave', {}, observedAtMs),
    heartbeat: observedAtMs => record('heartbeat', {}, observedAtMs),
    visibility: (state, observedAtMs) => record('visibility', { state }, observedAtMs),
    focus: (isFocused, observedAtMs) => record('focus', { focused: isFocused }, observedAtMs),
    scroll: (payload, observedAtMs) => record('scroll', payload, observedAtMs),
    transcriptToggle: (expanded, observedAtMs) => record('transcript_toggle', { expanded }, observedAtMs),
    segmentVisible: (segmentId, observedAtMs) => record('segment_visible', { segment_id: segmentId }, observedAtMs),
    replayRange: (payload, observedAtMs) => record('replay_range', payload, observedAtMs),
    activeSeconds: () => Math.max(0, Math.floor(activeMs / 1000)),
    pendingCount: () => pendingEvents.length,
  }
}

export function useReviewTelemetry(options) {
  return createReviewTelemetry(options)
}
