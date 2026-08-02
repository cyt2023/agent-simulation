import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ProtocolIntegrityPanel from './ProtocolIntegrityPanel.vue'

describe('ProtocolIntegrityPanel', () => {
  it('renders protocol, integrity, and release evidence without claiming external signoff', () => {
    const wrapper = mount(ProtocolIntegrityPanel, {
      props: {
        dashboard: {
          protocol: {
            protocol_version: 'study1-v2',
            checksum: 'abc123',
            recording_mode: 'audio_only',
            feature_flags: { resync_enabled: false, video_enabled: false },
          },
          integrity_report: {
            status: 'technical_acceptance',
            errors: [],
            warnings: ['EXTERNAL_SIGNOFFS_INCOMPLETE'],
          },
          release: {
            release_id: 'study1-release',
            checksum: 'release-checksum',
          },
        },
      },
    })

    expect(wrapper.text()).toContain('study1-v2')
    expect(wrapper.text()).toContain('audio_only')
    expect(wrapper.text()).toContain('EXTERNAL_SIGNOFFS_INCOMPLETE')
    expect(wrapper.text()).not.toContain('Data collection ready')
  })
})
