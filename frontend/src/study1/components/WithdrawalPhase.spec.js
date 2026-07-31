import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'

import WithdrawalPhase from './WithdrawalPhase.vue'


it('submits an English withdrawal and retention request payload', async () => {
  const wrapper = mount(WithdrawalPhase, {
    props: {
      busy: false,
      sessionId: 'session-1',
      role: 'principal',
    },
  })

  expect(wrapper.text()).not.toMatch(/[\u3400-\u9fff]/)

  await wrapper.get('[data-test="withdrawal-reason"]').setValue('I want to withdraw my data.')
  await wrapper.get('[data-test="confirm-withdrawal"]').setValue(true)
  await wrapper.get('[data-test="submit-withdrawal"]').trigger('click')

  expect(wrapper.emitted('submit')).toEqual([[
    {
      request_type: 'withdrawal',
      reason: 'I want to withdraw my data.',
      confirmation: true,
    },
  ]])
})
