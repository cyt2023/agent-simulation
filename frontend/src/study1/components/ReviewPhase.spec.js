import { flushPromises, mount } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'

import ReviewPhase from './ReviewPhase.vue'


vi.mock('../services/study1Api.js', () => ({
  fetchReview: vi.fn(async () => ({
    summary: { content: 'T1 stated a route fact. [segment:seg-9]' },
    transcript: {
      content: JSON.stringify([
        {
          segment_id: 'seg-9',
          speaker: 'teammate_1',
          start_ms: 100,
          end_ms: 900,
          text: 'The north route is shorter.',
        },
      ]),
    },
  })),
  logReviewUiEvent: vi.fn(async () => ({ accepted: true })),
}))


it('renders B transcript JSON as timestamped attributed segments', async () => {
  const wrapper = mount(ReviewPhase, { props: { sessionId: 'session-1' } })
  await flushPromises()
  await wrapper.get('.transcript-toggle').trigger('click')

  expect(wrapper.get('#segment-seg-9').text()).toContain('00:00.100')
  expect(wrapper.get('#segment-seg-9').text()).toContain('T1')
  expect(wrapper.get('#segment-seg-9').text()).toContain('The north route is shorter.')
})
