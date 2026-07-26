import { describe, expect, it } from 'vitest'

import {
  buildSummaryRetryPayload,
  canEndMeeting,
  startCommandForPhase,
} from './mediaControls.js'


describe('Study 1 researcher media controls', () => {
  it('maps only authoritative media phases to lifecycle commands', () => {
    expect(startCommandForPhase('PROXY_MEETING')).toBe('START_PROXY_MEETING')
    expect(startCommandForPhase('HANDOFF')).toBe('BEGIN_HANDOFF')
    expect(startCommandForPhase('SYNC_MEETING')).toBe('START_SYNC_MEETING')
    expect(startCommandForPhase('PRE_VOTE')).toBeNull()
  })

  it('allows explicit meeting end only for active meeting phases', () => {
    expect(canEndMeeting('PROXY_MEETING')).toBe(true)
    expect(canEndMeeting('SYNC_MEETING')).toBe(true)
    expect(canEndMeeting('HANDOFF')).toBe(false)
  })

  it('requires an auditable reason and fixed source versions for summary retry', () => {
    expect(() => buildSummaryRetryPayload('', {})).toThrow('reason')
    expect(() => buildSummaryRetryPayload('ASR correction', {})).toThrow('source transcript')
    expect(buildSummaryRetryPayload('ASR correction', {
      transcript_checksum: 'abc123',
      summary_version: '2',
    })).toEqual({
      reason: 'ASR correction',
      source_transcript_checksum: 'abc123',
      source_summary_version: '2',
    })
  })
})
