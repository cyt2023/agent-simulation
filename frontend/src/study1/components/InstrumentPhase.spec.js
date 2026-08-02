import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import InstrumentPhase from './InstrumentPhase.vue'

function postSurveyInstrument() {
  return {
    instrument_definition_id: 'post-survey-v2',
    instrument_version: '2.0',
    items: [
      {
        item_id: 'understanding',
        prompt: 'Rate your understanding.',
        response_type: 'integer',
        constraints: { min: 1, max: 7 },
        required: true,
      },
      {
        item_id: 'comments',
        prompt: 'Add any comments.',
        response_type: 'text',
        constraints: { max_length: 4000 },
        required: false,
      },
    ],
  }
}

describe('InstrumentPhase', () => {
  it('renders server-defined items in order and emits ordered responses', async () => {
    const wrapper = mount(InstrumentPhase, {
      props: { instrument: postSurveyInstrument(), title: 'Final questionnaire' },
    })

    expect(wrapper.findAll('[data-test="instrument-item"]').map(item => item.text())).toEqual([
      expect.stringContaining('Rate your understanding.'),
      expect.stringContaining('Add any comments.'),
    ])

    await wrapper.get('[data-test="instrument-understanding"]').setValue(6)
    await wrapper.get('[data-test="instrument-comments"]').setValue('No extra comments.')
    await wrapper.get('[data-test="submit-instrument"]').trigger('click')

    expect(wrapper.emitted('submit')[0][0]).toEqual({
      instrument_definition_id: 'post-survey-v2',
      instrument_version: '2.0',
      ordered_responses: [
        { item_id: 'understanding', response: 6 },
        { item_id: 'comments', response: 'No extra comments.' },
      ],
    })
  })

  it('does not allow submission when the server capability is disabled', async () => {
    const wrapper = mount(InstrumentPhase, {
      props: {
        instrument: postSurveyInstrument(),
        available: false,
      },
    })

    expect(wrapper.text()).toContain('This action is not available')
    expect(wrapper.get('[data-test="submit-instrument"]').attributes('disabled')).toBeDefined()
  })
})
