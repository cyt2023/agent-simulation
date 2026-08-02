import { describe, expect, it, vi } from 'vitest'

describe('useLiveKitTelemetry', () => {
  it('samples on demand and keeps telemetry local unless a consumer is provided', async () => {
    let telemetryModule = {}
    try {
      telemetryModule = await import('./useLiveKitTelemetry.js')
    } catch {}
    expect(telemetryModule.useLiveKitTelemetry).toBeTypeOf('function')

    const sample = { sampled_at: '2026-07-29T00:00:00.000Z', connection_state: 'connected' }
    const adapter = { sample: vi.fn(async () => sample) }
    const telemetry = telemetryModule.useLiveKitTelemetry({ adapter })

    await telemetry.sampleNow()

    expect(adapter.sample).toHaveBeenCalledOnce()
    expect(telemetry.latest.value).toEqual(sample)
    expect(telemetry.samples.value).toEqual([sample])
  })
})
