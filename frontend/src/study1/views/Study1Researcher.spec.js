import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'

import Study1FilePicker from '../components/Study1FilePicker.vue'
import Study1Researcher from './Study1Researcher.vue'
import { getStudy1Identity, listStudy1Sessions } from '../services/study1Api.js'


vi.mock('../services/study1Api.js', () => ({
  addStudy1Incident: vi.fn(),
  completeMockMedia: vi.fn(),
  controlStudy1Session: vi.fn(),
  createStudy1Session: vi.fn(),
  exportStudy1Data: vi.fn(),
  fetchMediaStatus: vi.fn(),
  fetchResearcherDashboard: vi.fn(),
  getStudy1Identity: vi.fn(),
  issueStudy1MediaCommand: vi.fn(),
  listStudy1Sessions: vi.fn(),
  researcherLogin: vi.fn(),
  transitionPhase: vi.fn(),
  uploadStudy1Materials: vi.fn(),
}))

vi.mock('../services/study1Socket.js', () => ({
  joinStudy1Session: vi.fn(),
  leaveStudy1Session: vi.fn(),
  offStudy1Event: vi.fn(),
  onStudy1Event: vi.fn(),
}))

beforeEach(() => vi.clearAllMocks())

it('marks the unauthenticated sign-in card as centered', () => {
  getStudy1Identity.mockReturnValue(null)
  const wrapper = mount(Study1Researcher)

  expect(wrapper.get('.login').classes()).toContain('login-centered')
  wrapper.unmount()
})

it('uses three English custom material uploaders', async () => {
  getStudy1Identity.mockReturnValue({ role: 'researcher' })
  listStudy1Sessions.mockResolvedValue({ sessions: [] })
  const wrapper = mount(Study1Researcher)
  await flushPromises()

  expect(wrapper.findAllComponents(Study1FilePicker)).toHaveLength(3)
  expect(wrapper.text()).toContain('Choose files')
  wrapper.unmount()
})
