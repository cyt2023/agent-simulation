import { describe, expect, it } from 'vitest'

describe('livekitStatsAdapter', () => {
  it('samples only locally observed LiveKit room state', async () => {
    let adapterModule = {}
    try {
      adapterModule = await import('./livekitStatsAdapter.js')
    } catch {}
    expect(adapterModule.createLiveKitStatsAdapter).toBeTypeOf('function')

    const room = {
      state: 'connected',
      localParticipant: { isSpeaking: false, audioLevel: 0.12 },
      remoteParticipants: new Map([
        ['t1', { identity: 'teammate_1', isSpeaking: true, audioLevel: 0.48 }],
      ]),
    }
    const sample = await adapterModule.createLiveKitStatsAdapter(room).sample()

    expect(sample).toMatchObject({
      connection_state: 'connected',
      remote_participant_count: 1,
      local: { is_speaking: false, audio_level: 0.12 },
    })
    expect(sample.remotes).toEqual([
      { identity: 'teammate_1', is_speaking: true, audio_level: 0.48 },
    ])
    expect(sample).not.toHaveProperty('backend_status')
  })
})
