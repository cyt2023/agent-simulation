const LOCAL_EXTENSION_LOADERS = Object.freeze({})

export const STUDY_EXTENSION_ALLOWLIST = Object.freeze(
  Object.keys(LOCAL_EXTENSION_LOADERS),
)

export function isStudyExtensionAllowed(moduleId) {
  return STUDY_EXTENSION_ALLOWLIST.includes(String(moduleId || ''))
}

export async function loadStudyExtension(moduleId) {
  if (!isStudyExtensionAllowed(moduleId)) return null
  const loader = LOCAL_EXTENSION_LOADERS[moduleId]
  return loader ? loader() : null
}
