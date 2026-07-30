import { computed, ref } from 'vue'
import { Room, RoomEvent } from 'livekit-client'

import { fetchMediaAccess } from '../services/study1Api.js'
import { createLiveKitStatsAdapter } from '../services/livekitStatsAdapter.js'
import { useLiveKitTelemetry } from './useLiveKitTelemetry.js'

const TEAMMATE_BRIDGE_PHASES = new Set([
  'PROXY_MEETING',
  'TENTATIVE_DECISION',
  'DELEGATION_EXPECTATION',
  'REVIEW',
  'COMPREHENSION_MEASUREMENT',
])
const AUDIO_PHASES = new Set(['PROXY_MEETING', 'HANDOFF', 'SYNC_MEETING'])
const RECONNECT_WINDOW_MS = 30_000

export function useStableAudioSession(options = {}) {
  const createRoom = options.createRoom || (() => new Room({ adaptiveStream: true, dynacast: false }))
  const events = options.roomEvents || RoomEvent
  const requestAccess = options.fetchAccess || fetchMediaAccess
  const createStatsAdapter = options.createStatsAdapter || createLiveKitStatsAdapter
  const createTelemetry = options.createTelemetry || useLiveKitTelemetry
  const telemetryIntervalMs = options.telemetryIntervalMs || 5_000
  const onTelemetrySample = options.onTelemetrySample || null

  const connectionState = ref('disconnected')
  const reconnectSecondsRemaining = ref(0)
  const muted = ref(false)
  const error = ref('')
  const remoteIdentities = ref(new Set())
  const activeIdentities = ref(new Set())
  const roomName = ref('')
  const currentContext = ref(null)
  const audioHost = ref(null)
  const outputDevices = ref([])
  const selectedOutputId = ref('')
  const outputSupported = ref(
    typeof HTMLMediaElement !== 'undefined'
      && typeof HTMLMediaElement.prototype?.setSinkId === 'function',
  )
  const outputNotice = ref('')

  let room = null
  let generation = 0
  let reconnectDeadline = 0
  let reconnectTimer = null
  let roomTelemetry = null
  let telemetryRoom = null

  const connected = computed(() => connectionState.value === 'connected')

  function clearReconnectWindow() {
    if (reconnectTimer) window.clearInterval(reconnectTimer)
    reconnectTimer = null
    reconnectDeadline = 0
    reconnectSecondsRemaining.value = 0
  }

  async function updateReconnectCountdown() {
    const remaining = Math.max(0, reconnectDeadline - Date.now())
    reconnectSecondsRemaining.value = Math.ceil(remaining / 1000)
    if (remaining > 0) return
    clearReconnectWindow()
    ++generation
    const failedRoom = room
    await releaseRoom(failedRoom)
    connectionState.value = 'reconnect_failed'
    error.value = 'Unable to restore the audio connection within 30 seconds.'
  }

  function startReconnectWindow() {
    clearReconnectWindow()
    connectionState.value = 'reconnecting'
    error.value = ''
    reconnectDeadline = Date.now() + RECONNECT_WINDOW_MS
    reconnectSecondsRemaining.value = 30
    reconnectTimer = window.setInterval(updateReconnectCountdown, 1000)
  }

  function participantIdentity(participant) {
    return participant?.name || participant?.identity || ''
  }

  function syncParticipants() {
    if (!room) return
    remoteIdentities.value = new Set(
      [...room.remoteParticipants.values()].map(participantIdentity).filter(Boolean),
    )
  }

  function clearAttachedAudio() {
    audioHost.value
      ?.querySelectorAll?.('[data-study1-remote-audio]')
      .forEach(element => element.remove())
  }

  function stopRoomTelemetry(target = null) {
    if (target && telemetryRoom && telemetryRoom !== target) return
    roomTelemetry?.stop()
    roomTelemetry = null
    telemetryRoom = null
  }

  function startRoomTelemetry(target) {
    if (telemetryRoom !== target) {
      stopRoomTelemetry()
      telemetryRoom = target
      roomTelemetry = createTelemetry({
        adapter: createStatsAdapter(target),
        intervalMs: telemetryIntervalMs,
        onSample: sample => onTelemetrySample?.({
          ...sample,
          phase: currentContext.value?.phase || '',
          phase_version: Number(currentContext.value?.phaseVersion) || 0,
          room_name: roomName.value,
        }),
      })
    }
    roomTelemetry.start()
  }

  async function releaseRoom(target = room) {
    if (!target) return
    if (room === target) {
      room = null
      roomName.value = ''
      stopRoomTelemetry(target)
      remoteIdentities.value = new Set()
      activeIdentities.value = new Set()
      clearAttachedAudio()
    }
    try {
      await target.disconnect()
    } catch {
      // Local state is still discarded so a later Join always creates a clean Room.
    }
  }

  function attachTrack(track) {
    const element = track.attach()
    element.autoplay = true
    element.dataset.study1RemoteAudio = 'true'
    audioHost.value?.appendChild(element)
    if (selectedOutputId.value && typeof element.setSinkId === 'function') {
      element.setSinkId(selectedOutputId.value).catch(() => {
        outputNotice.value = 'Unable to use the selected audio output.'
      })
    }
  }

  function detachTrack(track) {
    track.detach().forEach(element => element.remove())
  }

  function registerRoomHandlers(target) {
    target
      .on(events.TrackSubscribed, track => {
        if (target === room) attachTrack(track)
      })
      .on(events.TrackUnsubscribed, detachTrack)
      .on(events.ActiveSpeakersChanged, speakers => {
        if (target !== room) return
        const localRole = currentContext.value?.role
        activeIdentities.value = new Set(
          speakers
            .map(participantIdentity)
            .filter(identity => identity && !(muted.value && identity === localRole)),
        )
      })
      .on(events.ParticipantConnected, () => {
        if (target === room) syncParticipants()
      })
      .on(events.ParticipantDisconnected, () => {
        if (target === room) syncParticipants()
      })

    if (events.Reconnecting) {
      target.on(events.Reconnecting, () => {
        if (target === room) startReconnectWindow()
      })
    }
    if (events.Reconnected) {
      target.on(events.Reconnected, () => {
        if (target !== room) return
        clearReconnectWindow()
        connectionState.value = 'connected'
        error.value = ''
        syncParticipants()
      })
    }
    if (events.Disconnected) {
      target.on(events.Disconnected, () => {
        if (target !== room) return
        clearReconnectWindow()
        stopRoomTelemetry(target)
        room = null
        roomName.value = ''
        connectionState.value = 'disconnected'
        remoteIdentities.value = new Set()
        activeIdentities.value = new Set()
        clearAttachedAudio()
        if (currentContext.value) {
          error.value = 'The audio connection ended. Rejoin when you are ready.'
        }
      })
    }
    if (events.ConnectionStateChanged) {
      target.on(events.ConnectionStateChanged, state => {
        if (target !== room) return
        const normalized = String(state).toLowerCase()
        if (normalized === 'connected') connectionState.value = 'connected'
      })
    }
  }

  function ensureRoom() {
    if (!room) {
      room = createRoom()
      registerRoomHandlers(room)
    }
    return room
  }

  async function connect(context) {
    const requested = { ...context }
    const requestGeneration = ++generation
    const wasConnected = connectionState.value === 'connected'
    const previousRoomName = roomName.value
    currentContext.value = requested
    connectionState.value = 'connecting'
    error.value = ''
    let target = null
    try {
      const access = await requestAccess(requested.sessionId)
      if (access.available === false) throw new Error('Live media is not enabled for this session.')
      if (requestGeneration !== generation) return false

      target = ensureRoom()
      const sameConnectedRoom = wasConnected
        && Boolean(previousRoomName)
        && previousRoomName === access.room_name
      if (previousRoomName && previousRoomName !== access.room_name) {
        await releaseRoom(target)
        target = ensureRoom()
      }
      if (requestGeneration !== generation) {
        await releaseRoom(target)
        return false
      }
      if (!sameConnectedRoom) {
        await target.connect(access.url, access.token)
      }
      if (requestGeneration !== generation) {
        await releaseRoom(target)
        return false
      }
      await target.localParticipant.setMicrophoneEnabled(
        !muted.value,
        { deviceId: requested.deviceId },
      )
      roomName.value = access.room_name || ''
      connectionState.value = 'connected'
      syncParticipants()
      startRoomTelemetry(target)
      return true
    } catch (reason) {
      if (requestGeneration === generation) {
        await releaseRoom(target || room)
        connectionState.value = 'disconnected'
        error.value = reason?.message || 'Unable to join the audio meeting.'
      }
      return false
    }
  }

  async function disconnect() {
    ++generation
    clearReconnectWindow()
    await releaseRoom(room)
    connectionState.value = 'disconnected'
    error.value = ''
  }

  async function syncAuthoritativePhase(phase, phaseVersion, role) {
    const previous = currentContext.value
    if (previous) currentContext.value = { ...previous, phase, phaseVersion, role }
    const isTeammate = role === 'teammate_1' || role === 'teammate_2'
    if (['disconnected', 'reconnect_failed'].includes(connectionState.value)) return
    if (connectionState.value === 'reconnecting') {
      if ((isTeammate && TEAMMATE_BRIDGE_PHASES.has(phase)) || AUDIO_PHASES.has(phase)) return
      await disconnect()
      return
    }

    if (isTeammate && TEAMMATE_BRIDGE_PHASES.has(phase)) return

    if (AUDIO_PHASES.has(phase) && previous?.deviceId) {
      await connect({ ...previous, phase, phaseVersion, role })
      return
    }
    await disconnect()
  }

  async function toggleMute() {
    if (!room || connectionState.value !== 'connected') return false
    const nextMuted = !muted.value
    try {
      await room.localParticipant.setMicrophoneEnabled(
        !nextMuted,
        { deviceId: currentContext.value?.deviceId || '' },
      )
      muted.value = nextMuted
      if (nextMuted && currentContext.value?.role) {
        const nextActive = new Set(activeIdentities.value)
        nextActive.delete(currentContext.value.role)
        activeIdentities.value = nextActive
      }
      return true
    } catch (reason) {
      error.value = reason?.message || 'Unable to change the microphone state.'
      return false
    }
  }

  function setAudioHost(element) {
    audioHost.value = element
  }

  function configureOutputDevices(devices) {
    outputDevices.value = (devices || []).filter(device => device.kind === 'audiooutput')
  }

  async function setOutputDevice(deviceId) {
    const cleanDeviceId = String(deviceId || '')
    const elements = [...new Set(
      audioHost.value?.querySelectorAll?.('[data-study1-remote-audio], audio') || [],
    )]
    const canSetEverySink = elements.every(element => typeof element.setSinkId === 'function')
    if (!canSetEverySink || (!elements.length && !outputSupported.value)) {
      outputSupported.value = false
      outputNotice.value = 'Output selection is not supported by this browser.'
      return false
    }
    try {
      await Promise.all(elements.map(element => element.setSinkId(cleanDeviceId)))
      selectedOutputId.value = cleanDeviceId
      outputSupported.value = true
      outputNotice.value = ''
      return true
    } catch {
      outputNotice.value = 'Unable to use the selected audio output.'
      return false
    }
  }

  async function dispose() {
    await disconnect()
    currentContext.value = null
  }

  return {
    connectionState,
    reconnectSecondsRemaining,
    muted,
    error,
    remoteIdentities,
    activeIdentities,
    roomName,
    outputDevices,
    selectedOutputId,
    outputSupported,
    outputNotice,
    connected,
    connect,
    disconnect,
    syncAuthoritativePhase,
    toggleMute,
    setAudioHost,
    configureOutputDevices,
    setOutputDevice,
    dispose,
  }
}
