const WINDOWS_CHANNELS = [
  {
    channel: 'chrome',
    paths: [
      'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    ],
  },
  {
    channel: 'msedge',
    paths: [
      'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
      'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    ],
  },
]

const MAC_CHANNELS = [
  {
    channel: 'chrome',
    paths: ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'],
  },
  {
    channel: 'msedge',
    paths: ['/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'],
  },
]

const LINUX_CHANNELS = [
  {
    channel: 'chrome',
    paths: ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable'],
  },
  {
    channel: 'msedge',
    paths: ['/usr/bin/microsoft-edge', '/usr/bin/microsoft-edge-stable'],
  },
]

function localChannelsFor(platform) {
  if (platform === 'win32') return WINDOWS_CHANNELS
  if (platform === 'darwin') return MAC_CHANNELS
  if (platform === 'linux') return LINUX_CHANNELS
  return []
}

export function selectBrowserChannel({ env = process.env, platform = process.platform, exists } = {}) {
  if (env.PLAYWRIGHT_BROWSER_CHANNEL) return env.PLAYWRIGHT_BROWSER_CHANNEL
  if (env.CI) return undefined
  if (!exists) return undefined

  return localChannelsFor(platform).find((candidate) =>
    candidate.paths.some((path) => exists(path)),
  )?.channel
}
