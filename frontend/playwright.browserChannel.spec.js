import { describe, expect, it } from 'vitest'
import { selectBrowserChannel } from './playwright.browserChannel.js'

describe('selectBrowserChannel', () => {
  it('honors an explicit Playwright browser channel', () => {
    const channel = selectBrowserChannel({
      env: { PLAYWRIGHT_BROWSER_CHANNEL: 'msedge' },
      platform: 'win32',
      exists: () => false,
    })

    expect(channel).toBe('msedge')
  })

  it('uses installed Chrome on local Windows machines', () => {
    const channel = selectBrowserChannel({
      env: {},
      platform: 'win32',
      exists: (path) => path.includes('Google\\Chrome\\Application\\chrome.exe'),
    })

    expect(channel).toBe('chrome')
  })

  it('keeps CI on the bundled browser unless a channel is explicit', () => {
    const channel = selectBrowserChannel({
      env: { CI: 'true' },
      platform: 'win32',
      exists: () => true,
    })

    expect(channel).toBeUndefined()
  })
})
