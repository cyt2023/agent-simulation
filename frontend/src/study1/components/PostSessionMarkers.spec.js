import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import PostSessionMarkers from './PostSessionMarkers.vue'

describe('PostSessionMarkers', () => {
  it.each(['confusing', 'unexpected', 'uncomfortable', 'key_decision'])(
    'submits %s markers with a timestamp range and reason',
    async type => {
      const createMarker = vi.fn(async () => ({ marker_id: `marker-${type}` }))
      const wrapper = mount(PostSessionMarkers, {
        props: {
          sessionId: 'session-1',
          createMarker,
          fetchMarkers: vi.fn(async () => ({ markers: [] })),
        },
      })
      await flushPromises()

      await wrapper.get('[data-test="open-marker-dialog"]').trigger('click')
      await wrapper.get('[data-test="marker-type"]').setValue(type)
      await wrapper.get('[data-test="marker-start"]').setValue(12)
      await wrapper.get('[data-test="marker-end"]').setValue(18)
      await wrapper.get('[data-test="marker-reason"]').setValue('This moment should be discussed.')
      await wrapper.get('[data-test="submit-marker"]').trigger('click')
      await flushPromises()

      expect(createMarker).toHaveBeenCalledWith('session-1', {
        type,
        start_ms: 12_000,
        end_ms: 18_000,
        reason: 'This moment should be discussed.',
      })
    },
  )
})
