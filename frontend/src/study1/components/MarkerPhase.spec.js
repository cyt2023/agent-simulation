import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import MarkerPhase from './MarkerPhase.vue'

describe('MarkerPhase', () => {
  it('lets participants create typed post-session markers with millisecond ranges', async () => {
    const createMarker = vi.fn(async () => ({
      marker_id: 'marker-1',
      type: 'confusing',
      start_ms: 12000,
      end_ms: 18000,
      reason: 'The handoff explanation was hard to follow.',
    }))
    const wrapper = mount(MarkerPhase, {
      props: {
        sessionId: 'session-1',
        createMarker,
        fetchMarkers: vi.fn(async () => ({ markers: [] })),
      },
    })
    await flushPromises()

    await wrapper.get('[data-test="marker-type"]').setValue('confusing')
    await wrapper.get('[data-test="marker-start"]').setValue(12)
    await wrapper.get('[data-test="marker-end"]').setValue(18)
    await wrapper.get('[data-test="marker-reason"]').setValue('The handoff explanation was hard to follow.')
    await wrapper.get('[data-test="submit-marker"]').trigger('click')
    await flushPromises()

    expect(createMarker).toHaveBeenCalledWith('session-1', {
      type: 'confusing',
      start_ms: 12000,
      end_ms: 18000,
      reason: 'The handoff explanation was hard to follow.',
    })
  })
})
