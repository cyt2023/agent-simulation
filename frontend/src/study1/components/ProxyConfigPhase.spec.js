import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'

import ProxyConfigPhase from './ProxyConfigPhase.vue'


it('submits only explicitly authorized P material IDs', async () => {
  const wrapper = mount(ProxyConfigPhase, {
    props: {
      role: 'principal',
      materials: [
        { material_id: 'material-1', title: 'Route costs' },
        { material_id: 'material-2', title: 'Schedule risks' },
      ],
    },
  })

  await wrapper.get('[data-test="proxy-priorities"]').setValue('Protect the budget')
  await wrapper.get('[data-test="material-material-2"]').setValue(true)
  await wrapper.get('[data-test="authorization-confirmed"]').setValue(true)
  await wrapper.get('[data-test="submit-proxy-config"]').trigger('click')

  expect(wrapper.emitted('submit')).toEqual([[
    {
      priorities: 'Protect the budget',
      boundaries: '',
      authorization_confirmed: true,
      authorized_material_ids: ['material-2'],
    },
  ]])
})
