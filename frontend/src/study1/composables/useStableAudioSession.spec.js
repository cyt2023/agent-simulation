import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useStableAudioSession } from './useStableAudioSession.js'

const roomInstances = []

class FakeRoom {
  constructor() {
    this.handlers = new Map()
    this.remoteParticipants = new Map()
    this.state = 'disconnected'
    this.localParticipant = {
      identity: 'teammate_1',
      isSpeaking: false,
      audioLevel: 0.08,
      setMicrophoneEnabled: vi.fn(async () => undefined),
    }
    this.connect = vi.fn(async () => { this.state = 'connected' })
    this.disconnect = vi.fn(async () => { this.state = 'disconnected' })
    roomInstances.push(this)
  }

  on(event, handler) {
    this.handlers.set(event, handler)
    return this
  }

  emit(event, payload) {
    this.handlers.get(event)?.(payload)
  }
}

const roomEvents = {
  TrackSubscribed: 'trackSubscribed',
  TrackUnsubscribed: 'trackUnsubscribed',
  ActiveSpeakersChanged: 'activeSpeakersChanged',
  ParticipantConnected: 'participantConnected',
  ParticipantDisconnected: 'participantDisconnected',
  Reconnecting: 'reconnecting',
  Reconnected: 'reconnected',
  Disconnected: 'disconnected',
}

function createSession(
  fetchAccess = vi.fn(async () => ({
    url: 'ws://livekit',
    token: 'room-token',
    room_name: 'study1-session-1-audio',
  })),
  options = {},
) {
  return useStableAudioSession({
    createRoom: () => new FakeRoom(),
    roomEvents,
    fetchAccess,
    ...options,
  })
}

describe('useStableAudioSession', () => {
  beforeEach(() => {
    roomInstances.length = 0
    vi.useRealTimers()
  })

  it('keeps one Room connected for T1 and T2 across the private middle phases', async () => {
    const session = createSession()

    await session.connect({
      sessionId: 'session-1',
      phase: 'PROXY_MEETING',
      phaseVersion: 5,
      role: 'teammate_1',
      deviceId: 'mic-1',
    })
    await session.syncAuthoritativePhase('TENTATIVE_DECISION', 6, 'teammate_1')
    await session.syncAuthoritativePhase('DELEGATION_EXPECTATION', 7, 'teammate_1')
    await session.syncAuthoritativePhase('REVIEW', 8, 'teammate_1')
    await session.syncAuthoritativePhase('COMPREHENSION_MEASUREMENT', 9, 'teammate_1')

    expect(roomInstances).toHaveLength(1)
    expect(roomInstances[0].disconnect).not.toHaveBeenCalled()
    expect(session.connectionState.value).toBe('connected')
  })

  it('does not preserve the proxy room for P or after the experiment leaves the bridge phases', async () => {
    const session = createSession()
    await session.connect({
      sessionId: 'session-1',
      phase: 'SYNC_MEETING',
      phaseVersion: 11,
      role: 'principal',
      deviceId: 'mic-1',
    })

    await session.syncAuthoritativePhase('FINAL_DECISION', 12, 'principal')

    expect(roomInstances[0].disconnect).toHaveBeenCalledOnce()
    expect(session.connectionState.value).toBe('disconnected')
  })

  it('keeps the same Room connection from handoff into the synchronous meeting', async () => {
    const fetchAccess = vi.fn(async () => ({
      url: 'ws://livekit', token: 'sync-token', room_name: 'study1-session-1-audio',
    }))
    const session = createSession(fetchAccess)
    await session.connect({
      sessionId: 'session-1', phase: 'HANDOFF', phaseVersion: 10,
      role: 'teammate_1', deviceId: 'mic-1',
    })

    await session.syncAuthoritativePhase('SYNC_MEETING', 11, 'teammate_1')

    expect(roomInstances).toHaveLength(1)
    expect(roomInstances[0].connect).toHaveBeenCalledOnce()
    expect(roomInstances[0].disconnect).not.toHaveBeenCalled()
    expect(session.connectionState.value).toBe('connected')
  })

  it('applies an output device to attached remote audio with setSinkId', async () => {
    const session = createSession()
    const remoteAudio = { setSinkId: vi.fn(async () => undefined) }
    session.setAudioHost({ querySelectorAll: () => [remoteAudio] })

    const changed = await session.setOutputDevice('speaker-2')

    expect(changed).toBe(true)
    expect(remoteAudio.setSinkId).toHaveBeenCalledWith('speaker-2')
    expect(session.selectedOutputId.value).toBe('speaker-2')
  })

  it('samples the actual connected Room and forwards participant telemetry', async () => {
    const onTelemetrySample = vi.fn(async () => undefined)
    const session = createSession(undefined, {
      onTelemetrySample,
      telemetryIntervalMs: 60_000,
    })

    await session.connect({
      sessionId: 'session-1', phase: 'PROXY_MEETING', phaseVersion: 5,
      role: 'teammate_1', deviceId: 'mic-1',
    })

    await vi.waitFor(() => expect(onTelemetrySample).toHaveBeenCalledOnce())
    expect(onTelemetrySample).toHaveBeenCalledWith(expect.objectContaining({
      connection_state: 'connected',
      phase: 'PROXY_MEETING',
      phase_version: 5,
      room_name: 'study1-session-1-audio',
      local: expect.objectContaining({ identity: 'teammate_1' }),
    }))

    await session.dispose()
  })

  it('shows a bounded 30 second reconnect window and recovers without replacing the Room', async () => {
    vi.useFakeTimers()
    const session = createSession()
    await session.connect({
      sessionId: 'session-1', phase: 'PROXY_MEETING', phaseVersion: 5,
      role: 'teammate_1', deviceId: 'mic-1',
    })

    roomInstances[0].emit('reconnecting')
    expect(session.connectionState.value).toBe('reconnecting')
    expect(session.reconnectSecondsRemaining.value).toBe(30)

    await vi.advanceTimersByTimeAsync(10_000)
    expect(session.reconnectSecondsRemaining.value).toBe(20)
    roomInstances[0].emit('reconnected')

    expect(session.connectionState.value).toBe('connected')
    expect(session.reconnectSecondsRemaining.value).toBe(0)
    expect(roomInstances).toHaveLength(1)
    expect(roomInstances[0].disconnect).not.toHaveBeenCalled()
  })

  it('disconnects a recovering Room when the authoritative phase leaves audio', async () => {
    const session = createSession()
    await session.connect({
      sessionId: 'session-1', phase: 'SYNC_MEETING', phaseVersion: 11,
      role: 'teammate_1', deviceId: 'mic-1',
    })
    roomInstances[0].emit('reconnecting')

    await session.syncAuthoritativePhase('FINAL_DECISION', 12, 'teammate_1')

    expect(roomInstances[0].disconnect).toHaveBeenCalledOnce()
    expect(session.connectionState.value).toBe('disconnected')
  })

  it('ends a reconnect attempt after 30 seconds', async () => {
    vi.useFakeTimers()
    const session = createSession()
    await session.connect({
      sessionId: 'session-1', phase: 'PROXY_MEETING', phaseVersion: 5,
      role: 'teammate_2', deviceId: 'mic-1',
    })

    roomInstances[0].emit('reconnecting')
    await vi.advanceTimersByTimeAsync(30_000)

    expect(session.connectionState.value).toBe('reconnect_failed')
    expect(session.reconnectSecondsRemaining.value).toBe(0)
    expect(session.error.value).toBe('Unable to restore the audio connection within 30 seconds.')
    expect(roomInstances[0].disconnect).toHaveBeenCalledOnce()

    await session.connect({
      sessionId: 'session-1', phase: 'PROXY_MEETING', phaseVersion: 5,
      role: 'teammate_2', deviceId: 'mic-1',
    })
    expect(roomInstances).toHaveLength(2)
    expect(roomInstances[1].connect).toHaveBeenCalledOnce()
  })

  it('disposes a Room after connection setup fails and retries with a clean Room', async () => {
    const createRoom = vi.fn(() => {
      const candidate = new FakeRoom()
      if (createRoom.mock.calls.length === 1) {
        candidate.localParticipant.setMicrophoneEnabled.mockRejectedValueOnce(
          new Error('Microphone publication failed.'),
        )
      }
      return candidate
    })
    const session = createSession(undefined, { createRoom })
    const context = {
      sessionId: 'session-1', phase: 'PROXY_MEETING', phaseVersion: 5,
      role: 'teammate_1', deviceId: 'mic-1',
    }

    expect(await session.connect(context)).toBe(false)
    expect(roomInstances[0].disconnect).toHaveBeenCalledOnce()

    expect(await session.connect(context)).toBe(true)
    expect(roomInstances).toHaveLength(2)
    expect(roomInstances[1].connect).toHaveBeenCalledOnce()
  })

  it('disposes the connected Room when phase access refresh fails', async () => {
    const fetchAccess = vi.fn()
      .mockResolvedValueOnce({
        url: 'ws://livekit', token: 'room-token', room_name: 'study1-session-1-audio',
      })
      .mockRejectedValueOnce(new Error('Media access refresh failed.'))
    const session = createSession(fetchAccess)
    await session.connect({
      sessionId: 'session-1', phase: 'HANDOFF', phaseVersion: 10,
      role: 'teammate_1', deviceId: 'mic-1',
    })

    await session.syncAuthoritativePhase('SYNC_MEETING', 11, 'teammate_1')

    expect(roomInstances[0].disconnect).toHaveBeenCalledOnce()
    expect(session.connectionState.value).toBe('disconnected')
    expect(session.error.value).toBe('Media access refresh failed.')
  })
})
