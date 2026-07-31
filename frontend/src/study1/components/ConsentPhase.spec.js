import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'

import ConsentPhase from './ConsentPhase.vue'


it('submits separate audio-only consent scopes', async () => {
  const wrapper = mount(ConsentPhase, {
    props: {
      role: 'principal',
      consentVersion: 'consent-v2',
    },
  })

  await wrapper.get('[data-test="identity-confirmed"]').setValue(true)
  await wrapper.get('[data-test="role-confirmed"]').setValue(true)
  await wrapper.get('[data-test="scope-audio_recording"]').setValue(true)
  await wrapper.get('[data-test="scope-transcription"]').setValue(true)
  await wrapper.get('[data-test="scope-ui_telemetry"]').setValue(true)
  await wrapper.get('[data-test="scope-external_agent_processing"]').setValue(true)
  await wrapper.get('[data-test="voluntary-confirmed"]').setValue(true)
  await wrapper.get('[data-test="submit-consent"]').trigger('click')

  expect(wrapper.text()).not.toContain('video')
  expect(wrapper.emitted('submit')).toEqual([[
    {
      consent_version: 'consent-v2',
      identity_confirmed: true,
      role_confirmed: true,
      consent_scopes: {
        audio_recording: true,
        transcription: true,
        ui_telemetry: true,
        external_agent_processing: true,
      },
      voluntary_participation_confirmed: true,
    },
  ]])
})
