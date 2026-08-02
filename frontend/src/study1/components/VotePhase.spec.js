import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import VotePhase from './VotePhase.vue'

describe('VotePhase', () => {
  it('uses the three registered candidates rather than free text', () => {
    const wrapper = mount(VotePhase, {
      props: {
        candidates: ['candidate-a', 'candidate-b', 'candidate-c'],
      },
    })

    expect(wrapper.findAll('input[type="radio"]')).toHaveLength(3)
    expect(wrapper.find('input[type="text"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Candidate A')
    expect(wrapper.text()).toContain('Candidate B')
    expect(wrapper.text()).toContain('Candidate C')
  })

  it('emits the selected candidate id and rationale', async () => {
    const wrapper = mount(VotePhase, {
      props: {
        candidates: ['candidate-a', 'candidate-b', 'candidate-c'],
      },
    })

    await wrapper.get('input[value="candidate-b"]').setValue(true)
    await wrapper.get('textarea').setValue('Candidate B has the strongest combined evidence.')
    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('submit')[0][0]).toEqual({
      candidate_id: 'candidate-b',
      rationale: 'Candidate B has the strongest combined evidence.',
      confidence: 4,
    })
  })

  it('keeps the form unavailable when the server capability is disabled', async () => {
    const wrapper = mount(VotePhase, {
      props: {
        candidates: ['candidate-a'],
        available: false,
      },
    })

    expect(wrapper.text()).toContain('This action is not available')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.get('textarea').setValue('Should not submit.')
    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('submit')).toBeUndefined()
  })
})
