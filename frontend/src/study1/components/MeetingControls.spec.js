import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MeetingControls from './MeetingControls.vue'

describe('MeetingControls', () => {
  it('offers output selection and emits the selected sink ID', async () => {
    const wrapper = mount(MeetingControls, {
      props: {
        connectionState: 'connected',
        canJoin: true,
        outputSupported: true,
        selectedOutputId: 'speaker-1',
        outputDevices: [
          { deviceId: 'speaker-1', label: 'Desk speakers' },
          { deviceId: 'speaker-2', label: 'USB headset' },
        ],
      },
    })

    await wrapper.get('[data-test="audio-output"]').setValue('speaker-2')

    expect(wrapper.emitted('select-output')).toEqual([['speaker-2']])
    expect(wrapper.text()).not.toMatch(/camera|video|hand raise/i)
  })

  it('shows an explicit message when browser output selection is unsupported', () => {
    const wrapper = mount(MeetingControls, {
      props: {
        connectionState: 'connected',
        outputSupported: false,
      },
    })

    expect(wrapper.find('[data-test="audio-output"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Output selection is not supported by this browser.')
  })
})
