const START_COMMANDS = Object.freeze({
  PROXY_MEETING: 'START_PROXY_MEETING',
  HANDOFF: 'BEGIN_HANDOFF',
  SYNC_MEETING: 'START_SYNC_MEETING',
})

export function startCommandForPhase(phase) {
  return START_COMMANDS[phase] || null
}

export function canEndMeeting(phase) {
  return phase === 'PROXY_MEETING' || phase === 'SYNC_MEETING'
}

export function buildSummaryRetryPayload(reason, mediaStatus) {
  const cleanReason = String(reason || '').trim()
  if (!cleanReason) throw new Error('A reason is required for summary retry.')
  if (!mediaStatus?.transcript_checksum) {
    throw new Error('The source transcript checksum is unavailable.')
  }
  if (!mediaStatus?.summary_version) {
    throw new Error('The source summary version is unavailable.')
  }
  return {
    reason: cleanReason,
    source_transcript_checksum: mediaStatus.transcript_checksum,
    source_summary_version: String(mediaStatus.summary_version),
  }
}
