import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import Study1MeetingWorkspace from './Study1MeetingWorkspace.vue'

function audioSession(overrides = {}) {
  return {
    connectionState: { value: 'connected' },
    reconnectSecondsRemaining: { value: 0 },
    muted: { value: false },
    remoteIdentities: { value: new Set() },
    activeIdentities: { value: new Set() },
    error: { value: '' },
    connect: vi.fn(),
    toggleMute: vi.fn(),
    disconnect: vi.fn(),
    setAudioHost: vi.fn(),
    ...overrides,
  }
}

describe('Study1MeetingWorkspace', () => {
  it('orders T1, AI Proxy for P, and T2 in the delegated meeting', () => {
    const wrapper = mount(Study1MeetingWorkspace, {
      props: {
        sessionId: 'session-1',
        phase: 'PROXY_MEETING',
        phaseVersion: 5,
        role: 'teammate_1',
        audioSession: audioSession(),
      },
    })

    const seats = wrapper.findAll('[data-participant-seat]')
    expect(seats.map(seat => seat.attributes('data-role'))).toEqual([
      'teammate_1', 'proxy', 'teammate_2',
    ])
    expect(seats.map(seat => seat.text())).toEqual(expect.arrayContaining([
      expect.stringContaining('T1'),
      expect.stringContaining('AI Proxy for P'),
      expect.stringContaining('T2'),
    ]))
  })

  it('orders P, T1, and T2 in the synchronous meeting', () => {
    const wrapper = mount(Study1MeetingWorkspace, {
      props: {
        sessionId: 'session-1',
        phase: 'SYNC_MEETING',
        phaseVersion: 11,
        role: 'principal',
        audioSession: audioSession(),
      },
    })

    expect(wrapper.findAll('[data-participant-seat]').map(seat => seat.attributes('data-role'))).toEqual([
      'principal', 'teammate_1', 'teammate_2',
    ])
  })

  it('keeps three stable seats with an inactive placeholder during bridge phases', () => {
    const wrapper = mount(Study1MeetingWorkspace, {
      props: {
        sessionId: 'session-1',
        phase: 'REVIEW',
        phaseVersion: 8,
        role: 'teammate_1',
        audioSession: audioSession(),
      },
    })

    const seats = wrapper.findAll('[data-participant-seat]')
    expect(seats).toHaveLength(3)
    expect(seats.map(seat => seat.attributes('data-role'))).toEqual([
      'teammate_1', 'bridge_placeholder', 'teammate_2',
    ])
    expect(seats[1].attributes('data-placeholder')).toBe('true')
    expect(seats[1].classes()).not.toContain('active')
    expect(wrapper.text()).not.toContain('AI Proxy for P')
  })

  it('embeds audio devices and controls in the continuous dark meeting surface', () => {
    const wrapper = mount(Study1MeetingWorkspace, {
      props: {
        sessionId: 'session-1',
        phase: 'PROXY_MEETING',
        phaseVersion: 5,
        role: 'teammate_1',
        audioSession: audioSession(),
      },
    })

    expect(wrapper.get('.voice-room').classes()).toContain('embedded')
  })

  it('offers audio controls without video or camera commands', () => {
    const wrapper = mount(Study1MeetingWorkspace, {
      props: {
        sessionId: 'session-1',
        phase: 'HANDOFF',
        phaseVersion: 10,
        role: 'teammate_2',
        audioSession: audioSession({
          connectionState: { value: 'reconnecting' },
          reconnectSecondsRemaining: { value: 18 },
        }),
      },
    })

    expect(wrapper.text()).toContain('Reconnecting audio')
    expect(wrapper.text()).toContain('18s')
    expect(wrapper.text()).not.toContain('Video')
    expect(wrapper.text()).not.toContain('Camera')
  })
})
