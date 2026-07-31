import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  identity: {
    participant_id: 'participant-t1',
    session_id: 'session-1',
    role: 'teammate_1',
  },
  session: null,
  socketHandlers: {},
  stableSession: null,
  fetchMe: vi.fn(),
  logReviewUiEvent: vi.fn(),
  requestStudy1Withdrawal: vi.fn(),
  useStableAudioSession: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {} }),
  useRouter: () => ({ replace: vi.fn() }),
}))

vi.mock('../services/study1Api.js', () => ({
  clearStudy1Auth: vi.fn(),
  createSubmission: vi.fn(),
  exchangeInvite: vi.fn(),
  fetchMe: mocks.fetchMe,
  fetchMyMaterials: vi.fn(async () => ({ materials: [] })),
  getStudy1Identity: () => mocks.identity,
  logReviewUiEvent: mocks.logReviewUiEvent,
  requestStudy1Withdrawal: mocks.requestStudy1Withdrawal,
}))

vi.mock('../services/study1Socket.js', () => ({
  joinStudy1Session: vi.fn(),
  leaveStudy1Session: vi.fn(),
  offStudy1Event: vi.fn(),
  onStudy1Event: vi.fn((event, handler) => { mocks.socketHandlers[event] = handler }),
}))

vi.mock('../composables/useStableAudioSession.js', () => ({
  useStableAudioSession: mocks.useStableAudioSession,
}))

import Study1Participant from './Study1Participant.vue'

function session(phase, phaseVersion) {
  return {
    session_id: 'session-1',
    phase,
    phase_version: phaseVersion,
    status: 'running',
    ready_to_advance: false,
    remaining_seconds: 120,
    my_completed_actions: [],
  }
}

describe('Study1Participant stable meeting ownership', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.socketHandlers = {}
    mocks.session = session('PROXY_MEETING', 5)
    mocks.stableSession = {
      connectionState: ref('disconnected'),
      reconnectSecondsRemaining: ref(0),
      muted: ref(false),
      error: ref(''),
      remoteIdentities: ref(new Set()),
      activeIdentities: ref(new Set()),
      syncAuthoritativePhase: vi.fn(async () => undefined),
      dispose: vi.fn(async () => undefined),
    }
    mocks.useStableAudioSession.mockReturnValue(mocks.stableSession)
    mocks.logReviewUiEvent.mockResolvedValue({ event_id: 'event-1' })
    mocks.requestStudy1Withdrawal.mockResolvedValue({ accepted: true })
    mocks.fetchMe.mockImplementation(async () => ({
      identity: mocks.identity,
      session: mocks.session,
    }))
  })

  it('owns one audio session and keeps it through teammate bridge phases', async () => {
    const wrapper = mount(Study1Participant, {
      global: {
        stubs: {
          PhaseHeader: true,
          Study1MeetingWorkspace: {
            name: 'Study1MeetingWorkspace',
            props: ['audioSession'],
            template: '<div data-test="meeting-workspace" />',
          },
        },
      },
    })
    await flushPromises()

    expect(mocks.useStableAudioSession).toHaveBeenCalledOnce()
    expect(wrapper.getComponent({ name: 'Study1MeetingWorkspace' }).props('audioSession')).toBe(mocks.stableSession)

    mocks.session = session('TENTATIVE_DECISION', 6)
    await mocks.socketHandlers.study1_phase_updated({ session_id: 'session-1' })
    await flushPromises()
    mocks.session = session('REVIEW', 8)
    await mocks.socketHandlers.study1_phase_updated({ session_id: 'session-1' })
    await flushPromises()

    expect(mocks.stableSession.syncAuthoritativePhase).toHaveBeenCalledWith(
      'TENTATIVE_DECISION', 6, 'teammate_1',
    )
    expect(mocks.stableSession.syncAuthoritativePhase).toHaveBeenCalledWith(
      'REVIEW', 8, 'teammate_1',
    )
    expect(mocks.stableSession.dispose).not.toHaveBeenCalled()

    wrapper.unmount()
    expect(mocks.stableSession.dispose).toHaveBeenCalledOnce()
  })

  it('forwards connected Room telemetry through the participant UI event path', async () => {
    const wrapper = mount(Study1Participant, {
      global: {
        stubs: {
          PhaseHeader: true,
          Study1MeetingWorkspace: true,
        },
      },
    })
    await flushPromises()

    const options = mocks.useStableAudioSession.mock.calls[0][0]
    const sample = {
      sampled_at: '2026-07-29T00:00:00.000Z',
      connection_state: 'connected',
    }
    await options.onTelemetrySample(sample)

    expect(mocks.logReviewUiEvent).toHaveBeenCalledWith(
      'session-1',
      'rtc_metric_sample',
      sample,
    )
    wrapper.unmount()
  })

  it('lets participants submit withdrawal requests after completion', async () => {
    mocks.identity = {
      participant_id: 'participant-p',
      session_id: 'session-1',
      role: 'principal',
    }
    mocks.session = session('COMPLETED', 14)
    const wrapper = mount(Study1Participant, {
      global: {
        stubs: {
          PhaseHeader: true,
          CompletionPhase: true,
          Study1DeviceCheck: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('[data-test="withdrawal-reason"]').setValue('Please review withdrawal.')
    await wrapper.get('[data-test="confirm-withdrawal"]').setValue(true)
    await wrapper.get('[data-test="submit-withdrawal"]').trigger('click')
    await flushPromises()

    expect(mocks.requestStudy1Withdrawal).toHaveBeenCalledWith('session-1', {
      request_type: 'withdrawal',
      reason: 'Please review withdrawal.',
      confirmation: true,
    })
  })
})
