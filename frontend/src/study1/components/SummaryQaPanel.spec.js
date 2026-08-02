import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SummaryQaPanel from './SummaryQaPanel.vue'

describe('SummaryQaPanel', () => {
  it('submits coded summary QA ratings and requires a note for errors', async () => {
    const wrapper = mount(SummaryQaPanel)

    await wrapper.get('[data-test="summary-qa-artifact-id"]').setValue('summary-1')
    await wrapper.get('[data-test="summary-qa-omission"]').setValue(true)
    expect(wrapper.get('[data-test="summary-qa-submit"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-test="summary-qa-note"]').setValue('Missed a disagreement.')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')?.[0]).toEqual([{
      summary_artifact_id: 'summary-1',
      ratings: {
        omission_error: true,
        misattribution_error: false,
        hallucination_error: false,
        decision_status_error: false,
        action_item_error: false,
        note: 'Missed a disagreement.',
      },
    }])
  })
})
