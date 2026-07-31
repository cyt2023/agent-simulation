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
  fetchMyMaterials: vi.fn(),
  fetchCurrentInstrument: vi.fn(),
  submitIndividualDecision: vi.fn(),
  submitInstrumentResponse: vi.fn(),
  fetchSharedArtifact: vi.fn(),
  createSharedArtifactRevision: vi.fn(),
  confirmSharedArtifactRevision: vi.fn(),
  fetchMarkers: vi.fn(),
  createMarker: vi.fn(),
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
  fetchCurrentInstrument: mocks.fetchCurrentInstrument,
  fetchSharedArtifact: mocks.fetchSharedArtifact,
  fetchMarkers: mocks.fetchMarkers,
  createMarker: mocks.createMarker,
  fetchMe: mocks.fetchMe,
  fetchMyMaterials: mocks.fetchMyMaterials,
  getStudy1Identity: () => mocks.identity,
  logReviewUiEvent: mocks.logReviewUiEvent,
  requestStudy1Withdrawal: mocks.requestStudy1Withdrawal,
  submitIndividualDecision: mocks.submitIndividualDecision,
  submitInstrumentResponse: mocks.submitInstrumentResponse,
  createSharedArtifactRevision: mocks.createSharedArtifactRevision,
  confirmSharedArtifactRevision: mocks.confirmSharedArtifactRevision,
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
    capabilities: {
      submit_pre_individual: true,
      submit_tentative_individual: true,
      submit_final_individual: true,
      edit_team_final: true,
      confirm_team_final: true,
      edit_followup_task: true,
      confirm_followup_task: true,
      submit_post_survey: true,
      submit_delegation_expectation: true,
      submit_comprehension_measurement: true,
      material_read: false,
    },
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
    mocks.fetchMyMaterials.mockResolvedValue({ materials: [] })
    mocks.fetchCurrentInstrument.mockResolvedValue({
      instrument_definition_id: 'pre-individual-v2',
      instrument_version: '2.0',
      phase: 'PRE_VOTE',
      candidate_ids: ['candidate-a', 'candidate-b', 'candidate-c'],
      items: [],
    })
    mocks.submitIndividualDecision.mockResolvedValue({ decision_id: 'decision-1' })
    mocks.submitInstrumentResponse.mockResolvedValue({ response_id: 'response-1' })
    mocks.fetchSharedArtifact.mockResolvedValue({
      shared_artifact_id: null,
      kind: 'team_final',
      current_revision_id: null,
      current_revision: null,
      locked: false,
    })
    mocks.createSharedArtifactRevision.mockResolvedValue({ revision_id: 'revision-1' })
    mocks.confirmSharedArtifactRevision.mockResolvedValue({ revision_id: 'revision-1' })
    mocks.fetchMarkers.mockResolvedValue({ markers: [] })
    mocks.createMarker.mockResolvedValue({ marker_id: 'marker-1' })
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

  it('reloads and displays private materials during teammate proxy deliberation', async () => {
    mocks.session = {
      ...session('PROXY_MEETING', 5),
      capabilities: {
        ...session('PROXY_MEETING', 5).capabilities,
        material_read: true,
      },
    }
    mocks.fetchMyMaterials.mockResolvedValue({
      materials: [
        {
          material_id: 'material-t1',
          title: 'T1 private evidence',
          content: 'Only T1 can use this hidden profile fact.',
        },
      ],
    })
    const wrapper = mount(Study1Participant, {
      global: {
        stubs: {
          PhaseHeader: true,
          Study1MeetingWorkspace: {
            name: 'Study1MeetingWorkspace',
            template: '<div data-test="meeting-workspace"><slot /></div>',
          },
        },
      },
    })
    await flushPromises()

    expect(mocks.fetchMyMaterials).toHaveBeenCalledWith('session-1')
    expect(wrapper.text()).toContain('Your private material reference')
    expect(wrapper.text()).toContain('Only T1 can use this hidden profile fact.')
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

  it('shows post-session marker capture after completion', async () => {
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

    expect(wrapper.text()).toContain('Post-session markers')
    await wrapper.get('[data-test="marker-type"]').setValue('unexpected')
    await wrapper.get('[data-test="marker-start"]').setValue(30)
    await wrapper.get('[data-test="marker-end"]').setValue(45)
    await wrapper.get('[data-test="marker-reason"]').setValue('This moment should be replayed in the interview.')
    await wrapper.get('[data-test="submit-marker"]').trigger('click')
    await flushPromises()

    expect(mocks.createMarker).toHaveBeenCalledWith('session-1', {
      type: 'unexpected',
      start_ms: 30000,
      end_ms: 45000,
      reason: 'This moment should be replayed in the interview.',
    })
  })

  it('submits registered candidate decisions through the formal decision endpoint', async () => {
    mocks.identity = {
      participant_id: 'participant-p',
      session_id: 'session-1',
      role: 'principal',
    }
    mocks.session = session('PRE_VOTE', 2)
    const wrapper = mount(Study1Participant, {
      global: {
        stubs: {
          PhaseHeader: true,
          Study1DeviceCheck: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('input[value="candidate-b"]').setValue(true)
    await wrapper.get('textarea').setValue('Candidate B has the strongest evidence.')
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(mocks.submitIndividualDecision).toHaveBeenCalledWith(
      'session-1',
      'pre_individual',
      {
        candidate_id: 'candidate-b',
        rationale: 'Candidate B has the strongest evidence.',
        confidence: 4,
      },
    )
  })

  it('renders the shared team final workflow separately from private final decisions', async () => {
    mocks.identity = {
      participant_id: 'participant-p',
      session_id: 'session-1',
      role: 'principal',
    }
    mocks.session = session('FINAL_DECISION', 12)
    mocks.fetchCurrentInstrument.mockResolvedValue({
      instrument_definition_id: 'final-individual-v2',
      instrument_version: '2.0',
      phase: 'FINAL_DECISION',
      candidate_ids: ['candidate-a', 'candidate-b', 'candidate-c'],
      items: [],
    })
    const wrapper = mount(Study1Participant, {
      global: {
        stubs: {
          PhaseHeader: true,
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Private final decision')
    expect(wrapper.text()).toContain('Shared team final decision')
    await wrapper.get('[data-test="save-shared-revision"]').trigger('click')
    expect(mocks.createSharedArtifactRevision).not.toHaveBeenCalled()

    await wrapper.get('input[value="candidate-a"]').setValue(true)
    await wrapper.get('[data-test="shared-rationale"]').setValue('The team evidence supports Candidate A.')
    await wrapper.get('[data-test="save-shared-revision"]').trigger('click')
    await flushPromises()

    expect(mocks.createSharedArtifactRevision).toHaveBeenCalledWith(
      'session-1',
      'team_final',
      {
        parent_revision_id: null,
        content: expect.objectContaining({
          candidate_id: 'candidate-a',
          rationale: 'The team evidence supports Candidate A.',
        }),
      },
    )
  })

  it('honors disabled server capabilities for private final decisions', async () => {
    mocks.identity = {
      participant_id: 'participant-p',
      session_id: 'session-1',
      role: 'principal',
    }
    mocks.session = {
      ...session('FINAL_DECISION', 12),
      capabilities: {
        ...session('FINAL_DECISION', 12).capabilities,
        submit_final_individual: false,
      },
    }
    const wrapper = mount(Study1Participant, {
      global: {
        stubs: {
          PhaseHeader: true,
        },
      },
    })
    await flushPromises()

    await wrapper.get('input[value="candidate-a"]').setValue(true)
    await wrapper.get('textarea').setValue('Candidate A is best.')
    const privateDecisionButton = wrapper.findAll('button').find(button => button.text() === 'Submit and lock')
    expect(privateDecisionButton.attributes('disabled')).toBeDefined()
  })
})
