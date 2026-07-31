import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MediaHealthPanel from './MediaHealthPanel.vue'

describe('MediaHealthPanel', () => {
  it('shows Unknown rather than Ready when no ASR probe exists', () => {
    const wrapper = mount(MediaHealthPanel, {
      props: {
        mediaStatus: {
          service_status: 'ok',
          runtime_state: 'IDLE',
          components: { asr: { status: 'unknown' } },
        },
        qualitySnapshot: {
          rtc: { status: 'unknown' },
          components: { asr: { status: 'unknown' } },
        },
      },
    })

    expect(wrapper.text()).toContain('Unknown')
    expect(wrapper.text()).not.toContain('Ready')
  })

  it('renders audio-only connection and RTC quality details', () => {
    const wrapper = mount(MediaHealthPanel, {
      props: {
        mediaStatus: {
          service_status: 'ok',
          runtime_state: 'PROXY_ACTIVE',
          room_kind: 'proxy_meeting',
          room_name: 'study1-session-1-audio',
          pending_callback_count: 2,
          components: {
            recorder: { status: 'healthy' },
            asr: { status: 'healthy' },
            proxy: { status: 'degraded', last_error_code: 'LLM_TIMEOUT' },
          },
          connections: [
            {
              participant_id: 't1',
              role: 'teammate_1',
              state: 'connected',
              device: { label: 'USB microphone' },
            },
          ],
        },
        qualitySnapshot: {
          rtc: {
            status: 'degraded',
            fresh_participant_count: 2,
            stale_participant_count: 1,
            p50_rtt_ms: 120,
            p95_rtt_ms: 260,
          },
          components: {},
        },
      },
    })

    expect(wrapper.text()).toContain('study1-session-1-audio')
    expect(wrapper.text()).toContain('LLM_TIMEOUT')
    expect(wrapper.text()).toContain('p95 RTT 260 ms')
    expect(wrapper.find('video').exists()).toBe(false)
  })
})
