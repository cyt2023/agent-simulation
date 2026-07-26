import { getSocket } from '../../services/websocket.js'
import { getStudy1Token } from './study1Api.js'

const STUDY1_EVENTS = [
  'study1_phase_updated',
  'study1_readiness_updated',
  'study1_participant_status_updated',
  'study1_artifact_ready',
  'study1_incident_created',
  'study1_session_terminated',
]

let binding = null
let connectHandlerInstalled = false

function joinAuthoritatively() {
  if (!binding) return
  getSocket().emit('study1_join_session', {
    session_id: binding.sessionId,
    token: getStudy1Token(),
  })
}

export function joinStudy1Session(sessionId, onReconnect) {
  binding = { sessionId, onReconnect }
  const socket = getSocket()
  if (!connectHandlerInstalled) {
    socket.on('connect', () => {
      joinAuthoritatively()
      binding?.onReconnect?.()
    })
    connectHandlerInstalled = true
  }
  joinAuthoritatively()
}

export function leaveStudy1Session() {
  if (binding) {
    getSocket().emit('study1_leave_session', {
      session_id: binding.sessionId,
      token: getStudy1Token(),
    })
  }
  binding = null
}

export function onStudy1Event(eventName, handler) {
  if (!STUDY1_EVENTS.includes(eventName)) throw new Error(`Unknown Study 1 event: ${eventName}`)
  getSocket().on(eventName, handler)
}

export function offStudy1Event(eventName, handler) {
  getSocket().off(eventName, handler)
}

export { STUDY1_EVENTS }
