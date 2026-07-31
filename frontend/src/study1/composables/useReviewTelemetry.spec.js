import { describe, expect, it, vi } from 'vitest'

import { createReviewTelemetry } from './useReviewTelemetry.js'

describe('createReviewTelemetry', () => {
  it('does not count hidden-tab time as active reading', async () => {
    const sendBatch = vi.fn(async () => ({ accepted: true }))
    const telemetry = createReviewTelemetry({
      sessionId: 'session-1',
      visitId: 'visit-1',
      sendBatch,
    })

    await telemetry.enter(1_000)
    await telemetry.visibility('hidden', 2_000)
    await telemetry.heartbeat(22_000)

    expect(telemetry.activeSeconds()).toBe(0)
    expect(sendBatch).toHaveBeenLastCalledWith(
      'session-1',
      expect.objectContaining({
        visit_id: 'visit-1',
        events: [
          expect.objectContaining({
            event_type: 'heartbeat',
            observed_at_ms: 22_000,
          }),
        ],
      }),
    )
  })

  it('queues failed events and resends them with the next event', async () => {
    const sendBatch = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ accepted: true })
    const telemetry = createReviewTelemetry({
      sessionId: 'session-1',
      visitId: 'visit-1',
      sendBatch,
    })

    await telemetry.enter(1_000)
    await telemetry.heartbeat(6_000)

    expect(sendBatch).toHaveBeenLastCalledWith(
      'session-1',
      expect.objectContaining({
        events: [
          expect.objectContaining({ event_type: 'enter' }),
          expect.objectContaining({ event_type: 'heartbeat' }),
        ],
      }),
    )
    expect(telemetry.activeSeconds()).toBe(5)
  })
})
