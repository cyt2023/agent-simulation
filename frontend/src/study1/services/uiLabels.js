const CJK_PATTERN = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/u


export function displayMicrophoneLabel(label, index = 0) {
  const normalized = String(label || '').trim()
  if (!normalized || CJK_PATTERN.test(normalized)) return `Microphone ${index + 1}`
  return normalized
}

export function fileSelectionLabel(files) {
  const count = Array.from(files || []).length
  if (count === 0) return 'No files selected'
  if (count === 1) return '1 file selected'
  return `${count} files selected`
}
