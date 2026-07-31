import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StudyExtensionSlot from './StudyExtensionSlot.vue'
import { loadStudyExtension } from '../extensions/registry.js'

describe('StudyExtensionSlot', () => {
  it('renders no fallback or intelligent content when disabled', async () => {
    const wrapper = mount(StudyExtensionSlot, {
      props: { enabled: false, moduleId: 'study2.readonly' },
    })

    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toBe('')
    expect(wrapper.findComponent({ name: 'Study2ReadOnlyExtension' }).exists()).toBe(false)
  })

  it('does not load a module outside the local allowlist', async () => {
    await expect(loadStudyExtension('remote.resync')).resolves.toBeNull()
  })
})
