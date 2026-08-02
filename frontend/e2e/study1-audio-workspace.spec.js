import { expect, test } from '@playwright/test'

const sessionId = 'session-e2e'

async function seedStudy1Participant(page, viewportName) {
  await page.addInitScript(({ sessionId: seededSessionId }) => {
    window.sessionStorage.setItem('study1_auth_token', 'e2e-token')
    window.sessionStorage.setItem('study1_identity', JSON.stringify({
      participant_id: 't1-e2e',
      role: 'teammate_1',
      session_id: seededSessionId,
    }))
    Object.defineProperty(window.navigator, 'mediaDevices', {
      configurable: true,
      value: {
        async getUserMedia() {
          return { getTracks: () => [{ stop() {} }] }
        },
        async enumerateDevices() {
          return [
            {
              kind: 'audioinput',
              deviceId: `mic-${viewportName}`,
              label: 'E2E microphone',
            },
          ]
        },
      },
    })
  }, { sessionId, viewportName })

  await page.route('**/api/study1/sessions/*/me', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      identity: {
        participant_id: 't1-e2e',
        role: 'teammate_1',
        session_id: sessionId,
      },
      session: {
        session_id: sessionId,
        phase: 'PROXY_MEETING',
        phase_version: 1,
        status: 'running',
        ready_to_advance: false,
        remaining_seconds: 600,
        capabilities: {
          material_read: true,
          media_access: true,
        },
        my_completed_actions: [],
      },
    }),
  }))
  await page.route('**/api/study1/sessions/*/me/materials', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      materials: [
        {
          material_id: 'mat-t1',
          title: 'T1 private material',
          content: 'Private material remains available without exposing another role.',
        },
      ],
    }),
  }))
  await page.route('**/api/study1/sessions/*/media-access', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      url: 'ws://localhost:7880',
      token: 'e2e-livekit-token',
      room_name: 'study1-session-e2e-audio',
      publish_sources: ['microphone'],
    }),
  }))
  await page.route('**/socket.io/**', route => route.abort())
}

for (const viewport of [
  { name: 'desktop', width: 1280, height: 900 },
  { name: 'tablet', width: 820, height: 1180 },
  { name: 'mobile', width: 390, height: 844 },
]) {
  test(`Study 1 audio workspace stays neutral and audio-only on ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await seedStudy1Participant(page, viewport.name)

    await page.goto('/study1/participant')

    await expect(page.getByText('T1, the AI Proxy, and T2')).toBeVisible()
    await expect(page.getByText('AI Proxy for P')).toBeVisible()
    await expect(page.getByText('T1 private material')).toBeVisible()
    await expect(page.locator('video')).toHaveCount(0)
    await expect(page.getByText(/camera|video/i)).toHaveCount(0)
    await expect(page.locator('label[for="study1-microphone"]')).toHaveText('Microphone')
    await expect(page.getByRole('button', { name: /join audio/i })).toBeVisible()

    await page.screenshot({
      path: `test-results/study1-audio-workspace-${viewport.name}.png`,
      fullPage: true,
    })
  })
}
