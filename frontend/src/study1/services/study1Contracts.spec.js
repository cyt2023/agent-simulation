import { describe, expect, it } from 'vitest'

import {
  normalizeMediaAccess,
  normalizeParticipantState,
} from './study1Contracts.js'

describe('Study 1 formal contract normalizers', () => {
  it('normalizes server capabilities without inferring them from phase', () => {
    const value = normalizeParticipantState({
      phase: 'PRE_VOTE',
      capabilities: { submit_pre_individual: false },
    })

    expect(value.capabilities.submit_pre_individual).toBe(false)
    expect(value.capabilities.submit_final_decision).toBe(false)
  })

  it('rejects video media sources', () => {
    expect(() => normalizeMediaAccess({
      publish_sources: ['microphone', 'camera'],
    })).toThrow(/audio-only/i)
  })
})
