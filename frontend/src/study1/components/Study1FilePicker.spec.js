import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'

import Study1FilePicker from './Study1FilePicker.vue'


it('renders English file state and emits the selected files', async () => {
  const wrapper = mount(Study1FilePicker, { props: { inputId: 'p-files' } })
  expect(wrapper.text()).toContain('Choose files')
  expect(wrapper.text()).toContain('No files selected')

  const input = wrapper.get('input[type="file"]')
  const files = [new File(['a'], 'a.txt'), new File(['b'], 'b.md')]
  Object.defineProperty(input.element, 'files', { configurable: true, value: files })
  await input.trigger('change')

  expect(wrapper.text()).toContain('2 files selected')
  expect(wrapper.emitted('files-change')).toEqual([[files]])
})
