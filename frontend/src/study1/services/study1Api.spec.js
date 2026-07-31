import { beforeEach, expect, it, vi } from 'vitest'

import { researcherLogin } from './study1Api.js'


beforeEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})


it('can request scoped researcher tokens', async () => {
  const fetchMock = vi.fn(async () => new Response(
    JSON.stringify({ token: 'researcher-token' }),
    { status: 200, headers: { 'content-type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)

  await researcherLogin('researcher-key', ['operate', 'privacy_admin'])

  const body = JSON.parse(fetchMock.mock.calls[0][1].body)
  expect(body).toEqual({
    key: 'researcher-key',
    scopes: ['operate', 'privacy_admin'],
  })
})
