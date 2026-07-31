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

  it('keeps formal Study 1 capability names false until the server enables them', () => {
    const value = normalizeParticipantState({ phase: 'FINAL_DECISION' })

    expect(value.capabilities).toMatchObject({
      submit_tentative_individual: false,
      submit_final_individual: false,
      edit_team_final: false,
      confirm_team_final: false,
      edit_followup_task: false,
      confirm_followup_task: false,
    })
  })

  it('rejects video media sources', () => {
    expect(() => normalizeMediaAccess({
      publish_sources: ['microphone', 'camera'],
    })).toThrow(/audio-only/i)
  })
})
