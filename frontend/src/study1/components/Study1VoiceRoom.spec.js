import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Study1VoiceRoom from './Study1VoiceRoom.vue'
import { fetchMediaAccess } from '../services/study1Api.js'

const connect = vi.fn()
const disconnect = vi.fn()
const setMicrophoneEnabled = vi.fn()

vi.mock('livekit-client', () => ({
  Room: class {
    constructor() {
      this.localParticipant = { setMicrophoneEnabled }
      this.remoteParticipants = new Map()
    }
    on() { return this }
    connect(...args) { return connect(...args) }
    disconnect(...args) { return disconnect(...args) }
  },
  RoomEvent: {
    TrackSubscribed: 'trackSubscribed',
    TrackUnsubscribed: 'trackUnsubscribed',
    ActiveSpeakersChanged: 'activeSpeakersChanged',
    ConnectionStateChanged: 'connectionStateChanged',
    ParticipantConnected: 'participantConnected',
    ParticipantDisconnected: 'participantDisconnected',
  },
}))

vi.mock('../services/study1Api.js', () => ({
  fetchMediaAccess: vi.fn(async () => ({
    url: 'ws://livekit',
    token: 'short-lived-token',
    room_name: 'proxy-room',
    captions_enabled: false,
  })),
}))

describe('Study1VoiceRoom', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchMediaAccess.mockResolvedValue({
      url: 'ws://livekit',
      token: 'short-lived-token',
      room_name: 'proxy-room',
      captions_enabled: false,
    })
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => ({
          getTracks: () => [{ stop: vi.fn() }],
        })),
        enumerateDevices: vi.fn(async () => [
          { kind: 'audioinput', deviceId: 'mic-1', label: '默认 - 麦克风阵列' },
          { kind: 'audioinput', deviceId: 'mic-2', label: 'USB microphone' },
        ]),
      },
    })
  })

  it('checks a microphone before offering the join command', async () => {
    const wrapper = mount(Study1VoiceRoom, {
      props: {
        sessionId: 'session-1',
        phase: 'PROXY_MEETING',
        phaseVersion: 5,
        role: 'teammate_1',
      },
    })
    await flushPromises()

    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ audio: true })
    expect(wrapper.get('select').text()).toContain('Microphone 1')
    expect(wrapper.get('select').text()).toContain('USB microphone')
    expect(wrapper.get('select').text()).not.toContain('默认')
    expect(wrapper.get('[data-test="join-audio"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).not.toContain('Camera')
    expect(wrapper.text()).not.toContain('Screen')
    expect(wrapper.text()).not.toContain('Captions')
  })

  it('connects with the token returned by A and publishes only microphone audio', async () => {
    const wrapper = mount(Study1VoiceRoom, {
      props: {
        sessionId: 'session-1',
        phase: 'SYNC_MEETING',
        phaseVersion: 10,
        role: 'principal',
      },
    })
    await flushPromises()
    await wrapper.get('[data-test="join-audio"]').trigger('click')
    await flushPromises()

    expect(connect).toHaveBeenCalledWith('ws://livekit', 'short-lived-token')
    expect(setMicrophoneEnabled).toHaveBeenCalledWith(true, { deviceId: 'mic-1' })
  })

  it('disconnects when the authoritative phase version changes', async () => {
    const wrapper = mount(Study1VoiceRoom, {
      props: {
        sessionId: 'session-1',
        phase: 'SYNC_MEETING',
        phaseVersion: 10,
        role: 'teammate_1',
      },
    })
    await flushPromises()
    await wrapper.get('[data-test="join-audio"]').trigger('click')
    await flushPromises()
    await wrapper.setProps({ phaseVersion: 11 })
    await flushPromises()
    expect(disconnect).toHaveBeenCalled()
  })

  it('does not connect when access returns after a phase change', async () => {
    let releaseAccess
    fetchMediaAccess.mockImplementationOnce(() => new Promise(resolve => {
      releaseAccess = resolve
    }))
    const wrapper = mount(Study1VoiceRoom, {
      props: {
        sessionId: 'session-1',
        phase: 'SYNC_MEETING',
        phaseVersion: 10,
        role: 'principal',
      },
    })
    await flushPromises()

    wrapper.get('[data-test="join-audio"]').trigger('click')
    await flushPromises()
    await wrapper.setProps({ phaseVersion: 11 })
    releaseAccess({ url: 'ws://livekit', token: 'stale-token' })
    await flushPromises()

    expect(connect).not.toHaveBeenCalled()
    expect(setMicrophoneEnabled).not.toHaveBeenCalled()
  })
})
