import { describe, expect, it } from 'vitest'

import { displayMicrophoneLabel, fileSelectionLabel } from './uiLabels.js'


describe('Study 1 English UI labels', () => {
  it('replaces CJK and empty device labels with indexed English fallbacks', () => {
    expect(displayMicrophoneLabel('默认 - 麦克风阵列', 0)).toBe('Microphone 1')
    expect(displayMicrophoneLabel('', 1)).toBe('Microphone 2')
    expect(displayMicrophoneLabel('USB microphone', 2)).toBe('USB microphone')
  })

  it('describes file counts in English', () => {
    expect(fileSelectionLabel([])).toBe('No files selected')
    expect(fileSelectionLabel([{}])).toBe('1 file selected')
    expect(fileSelectionLabel([{}, {}])).toBe('2 files selected')
  })
})
