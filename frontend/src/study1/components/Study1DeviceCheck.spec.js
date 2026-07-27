import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'

import Study1DeviceCheck from './Study1DeviceCheck.vue'
import { reportMediaDevice } from '../services/study1Api.js'


vi.mock('../services/study1Api.js', () => ({
  reportMediaDevice: vi.fn(async () => ({ accepted: true })),
}))

beforeEach(() => {
  vi.clearAllMocks()
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })),
      enumerateDevices: vi.fn(async () => [
        { kind: 'audioinput', deviceId: 'mic-1', label: '默认 - 麦克风阵列' },
      ]),
    },
  })
})

it('reports a successful SETUP microphone check through A', async () => {
  const wrapper = mount(Study1DeviceCheck, {
    props: { sessionId: 'session-1' },
  })
  await flushPromises()

  expect(wrapper.text()).toContain('Microphone 1')
  expect(wrapper.text()).not.toContain('默认')
  expect(wrapper.text()).toContain('ready')
  expect(reportMediaDevice).toHaveBeenCalledWith('session-1', {
    state: 'ready',
    device: { kind: 'audioinput', label: '默认 - 麦克风阵列' },
  })
})
