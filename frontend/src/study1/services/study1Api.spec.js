import { beforeEach, expect, it, vi } from 'vitest'

import { researcherLogin, requestStudy1Withdrawal } from './study1Api.js'


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


it('posts withdrawal requests to the privacy endpoint', async () => {
  const fetchMock = vi.fn(async () => new Response(
    JSON.stringify({ accepted: true }),
    { status: 202, headers: { 'content-type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)

  await requestStudy1Withdrawal('session 1', {
    request_type: 'withdrawal',
    reason: 'Review withdrawal.',
    confirmation: true,
  })

  expect(fetchMock.mock.calls[0][0]).toBe('/api/study1/sessions/session%201/privacy/withdrawal-requests')
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
    request_type: 'withdrawal',
    reason: 'Review withdrawal.',
    confirmation: true,
  })
})
