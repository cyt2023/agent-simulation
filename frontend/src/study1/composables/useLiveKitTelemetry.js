import { ref } from 'vue'

export function useLiveKitTelemetry({ adapter, intervalMs = 5_000, onSample = null } = {}) {
  const latest = ref(null)
  const samples = ref([])
  const error = ref('')
  let timer = null

  async function sampleNow() {
    if (!adapter?.sample) return null
    try {
      const sample = await adapter.sample()
      latest.value = sample
      samples.value = [...samples.value.slice(-59), sample]
      error.value = ''
      await onSample?.(sample)
      return sample
    } catch (reason) {
      error.value = reason?.message || 'Unable to sample local audio telemetry.'
      return null
    }
  }

  function start() {
    if (timer) return
    sampleNow()
    timer = window.setInterval(sampleNow, intervalMs)
  }

  function stop() {
    if (timer) window.clearInterval(timer)
    timer = null
  }

  return { latest, samples, error, sampleNow, start, stop }
}
