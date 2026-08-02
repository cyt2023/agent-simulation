import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import PhaseHeader from './PhaseHeader.vue'

describe('PhaseHeader', () => {
  it('groups the protocol into a compact high-level rail and shows a readable countdown', () => {
    vi.useFakeTimers()
    const wrapper = mount(PhaseHeader, {
      props: {
        phase: 'PROXY_MEETING',
        status: 'running',
        remainingSeconds: 905,
      },
    })

    expect(wrapper.text()).toContain('Stage 3 of 5')
    expect(wrapper.text()).toContain('Delegated discussion')
    expect(wrapper.get('[data-test="phase-timer"]').text()).toBe('15:05')
    const stages = wrapper.findAll('[data-test="phase-rail-item"]')
    expect(stages).toHaveLength(5)
    expect(stages.map(stage => stage.text())).toEqual([
      expect.stringContaining('Preparation'),
      expect.stringContaining('Proxy setup'),
      expect.stringContaining('Delegated discussion'),
      expect.stringContaining('Review and handoff'),
      expect.stringContaining('Team completion'),
    ])
    expect(stages[1].attributes('data-state')).toBe('completed')
    expect(stages[2].attributes('data-state')).toBe('current')
    expect(stages[2].attributes('aria-current')).toBe('step')
    expect(stages[3].attributes('data-state')).toBe('upcoming')
    expect(wrapper.text()).not.toContain('Camera')
    expect(wrapper.text()).not.toContain('Video')
    vi.useRealTimers()
  })
})
