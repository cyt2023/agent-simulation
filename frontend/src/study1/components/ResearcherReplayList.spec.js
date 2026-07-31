import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ResearcherReplayList from './ResearcherReplayList.vue'

describe('ResearcherReplayList', () => {
  it('emits invisible researcher markers and replay plan requests', async () => {
    const wrapper = mount(ResearcherReplayList, {
      props: {
        markers: [
          { marker_id: 'marker-1', type: 'technical', start_ms: 10_000, end_ms: 12_000, reason: 'ASR gap' },
        ],
        replayPlans: [],
      },
    })

    await wrapper.get('[data-test="researcher-marker-type"]').setValue('technical')
    await wrapper.get('[data-test="researcher-marker-start"]').setValue(12)
    await wrapper.get('[data-test="researcher-marker-end"]').setValue(14)
    await wrapper.get('[data-test="researcher-marker-reason"]').setValue('ASR briefly dropped.')
    await wrapper.get('form.audit-form').trigger('submit')

    expect(wrapper.emitted('create-marker')?.[0]).toEqual([{
      type: 'technical',
      start_ms: 12_000,
      end_ms: 14_000,
      reason: 'ASR briefly dropped.',
      participant_visible: false,
    }])

    await wrapper.get('[data-test="researcher-replay-marker-ids"]').setValue('marker-1')
    await wrapper.get('[data-test="researcher-replay-context"]').setValue(8)
    await wrapper.get('form.replay-form').trigger('submit')

    expect(wrapper.emitted('create-replay-plan')?.[0]).toEqual([{
      marker_ids: ['marker-1'],
      context_seconds: 8,
    }])
  })
})
