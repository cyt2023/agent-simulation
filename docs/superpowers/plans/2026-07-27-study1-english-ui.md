# Study 1 English-Only UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Center the Study 1 researcher sign-in card and guarantee English-only visible UI across the new Study 1 researcher and participant surfaces.

**Architecture:** Add one UI-only label module for deterministic file-count and microphone labels, plus one focused accessible file-picker component. Study 1 views consume those primitives while retaining raw device labels for reporting and device IDs for selection. Legacy frontend routes and backend contracts remain untouched.

**Tech Stack:** Vue 3 Composition API, `@vue/test-utils`, Vitest, Vite, existing `@lucide/vue` icon library, Docker Compose.

---

## File map

- Create `frontend/src/study1/services/uiLabels.js`: pure English display-label functions.
- Create `frontend/src/study1/services/uiLabels.spec.js`: unit tests for CJK fallback and file counts.
- Create `frontend/src/study1/components/Study1FilePicker.vue`: accessible custom English file control.
- Create `frontend/src/study1/components/Study1FilePicker.spec.js`: file selection and visible-copy tests.
- Create `frontend/src/study1/views/Study1Researcher.spec.js`: researcher login layout and uploader integration tests.
- Modify `frontend/src/study1/views/Study1Researcher.vue`: centered login, custom uploaders, sanitized device display.
- Modify `frontend/src/study1/components/Study1DeviceCheck.vue`: sanitize rendered microphone label only.
- Modify `frontend/src/study1/components/Study1DeviceCheck.spec.js`: prove raw reporting and English rendering coexist.
- Modify `frontend/src/study1/components/Study1VoiceRoom.vue`: sanitize microphone option labels.
- Modify `frontend/src/study1/components/Study1VoiceRoom.spec.js`: prove Chinese OS labels never render.
- Create `frontend/src/study1/englishOnly.spec.js`: source-tree regression scan for CJK UI copy.

### Task 1: Add deterministic English UI-label helpers

**Files:**
- Create: `frontend/src/study1/services/uiLabels.spec.js`
- Create: `frontend/src/study1/services/uiLabels.js`

- [ ] **Step 1: Write the failing helper tests**

```js
import { describe, expect, it } from 'vitest'

import { displayMicrophoneLabel, fileSelectionLabel } from './uiLabels.js'

describe('Study 1 English UI labels', () => {
  it('replaces CJK and empty device labels with indexed English fallbacks', () => {
    expect(displayMicrophoneLabel('默认 - 麦克风阵列', 0)).toBe('Microphone 1')
    expect(displayMicrophoneLabel('', 1)).toBe('Microphone 2')
    expect(displayMicrophoneLabel('USB microphone', 2)).toBe('USB microphone')
  })

  it('describes file counts in English', () => {
    expect(fileSelectionLabel([])).toBe('No files selected')
    expect(fileSelectionLabel([{}])).toBe('1 file selected')
    expect(fileSelectionLabel([{}, {}])).toBe('2 files selected')
  })
})
```

- [ ] **Step 2: Run the helper tests and verify RED**

Run:

```powershell
npm --prefix frontend test -- --run src/study1/services/uiLabels.spec.js
```

Expected: FAIL because `uiLabels.js` does not exist.

- [ ] **Step 3: Implement the pure helpers**

```js
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
```

- [ ] **Step 4: Run the helper tests and verify GREEN**

Run the Step 2 command. Expected: 2 tests pass.

- [ ] **Step 5: Commit the helper boundary**

```powershell
git add frontend/src/study1/services/uiLabels.js frontend/src/study1/services/uiLabels.spec.js
git commit -m "feat: add Study 1 English UI labels"
```

### Task 2: Replace localized native file controls

**Files:**
- Create: `frontend/src/study1/components/Study1FilePicker.spec.js`
- Create: `frontend/src/study1/components/Study1FilePicker.vue`

- [ ] **Step 1: Write the failing file-picker test**

```js
import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'

import Study1FilePicker from './Study1FilePicker.vue'

it('renders English file state and emits the selected files', async () => {
  const wrapper = mount(Study1FilePicker, { props: { inputId: 'p-files' } })
  expect(wrapper.text()).toContain('Choose files')
  expect(wrapper.text()).toContain('No files selected')

  const input = wrapper.get('input[type="file"]')
  const files = [new File(['a'], 'a.txt'), new File(['b'], 'b.md')]
  Object.defineProperty(input.element, 'files', { configurable: true, value: files })
  await input.trigger('change')

  expect(wrapper.text()).toContain('2 files selected')
  expect(wrapper.emitted('files-change')).toEqual([[files]])
})
```

- [ ] **Step 2: Run the component test and verify RED**

```powershell
npm --prefix frontend test -- --run src/study1/components/Study1FilePicker.spec.js
```

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement the accessible English picker**

```vue
<script setup>
import { ref } from 'vue'
import { Upload } from '@lucide/vue'

import { fileSelectionLabel } from '../services/uiLabels.js'

defineProps({ inputId: { type: String, required: true } })
const emit = defineEmits(['files-change'])
const selectedFiles = ref([])

function selectFiles(event) {
  selectedFiles.value = Array.from(event.target.files || [])
  emit('files-change', selectedFiles.value)
}
</script>

<template>
  <div class="file-picker">
    <input
      :id="inputId"
      class="sr-only"
      type="file"
      accept=".pdf,.txt,.md"
      multiple
      @change="selectFiles"
    >
    <label class="file-button" :for="inputId">
      <Upload :size="17" aria-hidden="true" />
      Choose files
    </label>
    <span class="file-status" aria-live="polite">
      {{ fileSelectionLabel(selectedFiles) }}
    </span>
  </div>
</template>
```

Add these scoped styles:

```css
.file-picker { display:flex; align-items:center; flex-wrap:wrap; gap:.65rem; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
.file-button { display:inline-flex; align-items:center; gap:.45rem; padding:.6rem .75rem; border:1px solid #aebbc5; border-radius:7px; background:#fff; color:#334754; font-weight:700; cursor:pointer; }
.sr-only:focus-visible + .file-button { outline:3px solid rgba(38,95,140,.3); outline-offset:2px; }
.file-status { color:#667482; font-size:.9rem; font-weight:500; }
```

- [ ] **Step 4: Run the file-picker test and verify GREEN**

Run the Step 2 command. Expected: 1 test passes.

- [ ] **Step 5: Commit the file picker**

```powershell
git add frontend/src/study1/components/Study1FilePicker.vue frontend/src/study1/components/Study1FilePicker.spec.js
git commit -m "feat: add English Study 1 file picker"
```

### Task 3: Center the researcher sign-in and integrate English controls

**Files:**
- Create: `frontend/src/study1/views/Study1Researcher.spec.js`
- Modify: `frontend/src/study1/views/Study1Researcher.vue`

- [ ] **Step 1: Write failing researcher-view tests**

Use this complete test scaffold, setting `getStudy1Identity` to `null` for the
first test and to `{ role: 'researcher' }` for the second test:

```js
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'

import Study1FilePicker from '../components/Study1FilePicker.vue'
import Study1Researcher from './Study1Researcher.vue'
import { getStudy1Identity, listStudy1Sessions } from '../services/study1Api.js'

vi.mock('../services/study1Api.js', () => ({
  addStudy1Incident: vi.fn(),
  completeMockMedia: vi.fn(),
  controlStudy1Session: vi.fn(),
  createStudy1Session: vi.fn(),
  exportStudy1Data: vi.fn(),
  fetchMediaStatus: vi.fn(),
  fetchResearcherDashboard: vi.fn(),
  getStudy1Identity: vi.fn(),
  issueStudy1MediaCommand: vi.fn(),
  listStudy1Sessions: vi.fn(),
  researcherLogin: vi.fn(),
  transitionPhase: vi.fn(),
  uploadStudy1Materials: vi.fn(),
}))

vi.mock('../services/study1Socket.js', () => ({
  joinStudy1Session: vi.fn(),
  leaveStudy1Session: vi.fn(),
  offStudy1Event: vi.fn(),
  onStudy1Event: vi.fn(),
}))

beforeEach(() => vi.clearAllMocks())

it('marks the unauthenticated sign-in card as centered', () => {
  getStudy1Identity.mockReturnValue(null)
  const wrapper = mount(Study1Researcher)
  expect(wrapper.get('.login').classes()).toContain('login-centered')
})

it('uses three English custom material uploaders', async () => {
  getStudy1Identity.mockReturnValue({ role: 'researcher' })
  listStudy1Sessions.mockResolvedValue({ sessions: [] })
  const wrapper = mount(Study1Researcher)
  await flushPromises()
  expect(wrapper.findAllComponents(Study1FilePicker)).toHaveLength(3)
  expect(wrapper.text()).toContain('Choose files')
})
```

- [ ] **Step 2: Run the researcher tests and verify RED**

```powershell
npm --prefix frontend test -- --run src/study1/views/Study1Researcher.spec.js
```

Expected: FAIL because the card lacks `login-centered` and the native inputs are
still present.

- [ ] **Step 3: Implement the view integration**

Add imports:

```js
import Study1FilePicker from '../components/Study1FilePicker.vue'
import { displayMicrophoneLabel } from '../services/uiLabels.js'
```

Use the centered layout hook:

```vue
<section v-if="!authenticated" class="panel login login-centered">
```

Replace each visible native file input with:

```vue
<Study1FilePicker
  :input-id="`study1-material-${role}`"
  @files-change="materialFiles[role] = $event"
/>
```

Change the media connection loop to receive its index and render:

```vue
<tr v-for="(connection, index) in mediaStatus.connections" :key="connection.participant_id">
  <td>{{ connection.participant_id }}</td>
  <td>{{ connection.role }}</td>
  <td>{{ connection.state }}</td>
  <td>{{ displayMicrophoneLabel(connection.device?.label, index) }}</td>
</tr>
```

Add:

```css
.login-centered { width:min(460px,100%); margin:1.25rem auto; }
```

- [ ] **Step 4: Run researcher and file-picker tests**

```powershell
npm --prefix frontend test -- --run src/study1/views/Study1Researcher.spec.js src/study1/components/Study1FilePicker.spec.js
```

Expected: all targeted tests pass.

- [ ] **Step 5: Commit the researcher UI integration**

```powershell
git add frontend/src/study1/views/Study1Researcher.vue frontend/src/study1/views/Study1Researcher.spec.js
git commit -m "feat: center and anglicize Study 1 researcher UI"
```

### Task 4: Sanitize participant device labels without changing captured data

**Files:**
- Modify: `frontend/src/study1/components/Study1DeviceCheck.spec.js`
- Modify: `frontend/src/study1/components/Study1DeviceCheck.vue`
- Modify: `frontend/src/study1/components/Study1VoiceRoom.spec.js`
- Modify: `frontend/src/study1/components/Study1VoiceRoom.vue`

- [ ] **Step 1: Add failing CJK rendering tests**

In `Study1DeviceCheck.spec.js`, mock the microphone label as
`默认 - 麦克风阵列`, mount, and assert:

```js
expect(wrapper.text()).toContain('Microphone 1')
expect(wrapper.text()).not.toContain('默认')
expect(reportMediaDevice).toHaveBeenCalledWith('session-1', {
  state: 'ready',
  device: { kind: 'audioinput', label: '默认 - 麦克风阵列' },
})
```

In `Study1VoiceRoom.spec.js`, return two devices named `默认 - 麦克风阵列` and
`USB microphone`, then assert:

```js
expect(wrapper.get('select').text()).toContain('Microphone 1')
expect(wrapper.get('select').text()).toContain('USB microphone')
expect(wrapper.get('select').text()).not.toContain('默认')
```

- [ ] **Step 2: Run both component suites and verify RED**

```powershell
npm --prefix frontend test -- --run src/study1/components/Study1DeviceCheck.spec.js src/study1/components/Study1VoiceRoom.spec.js
```

Expected: FAIL because raw Chinese device names are rendered.

- [ ] **Step 3: Sanitize only the rendered labels**

Import `displayMicrophoneLabel` in both components. Keep `deviceLabel.value` and
the API report raw in `Study1DeviceCheck`, but render:

```vue
<strong>{{ displayMicrophoneLabel(deviceLabel, 0) }}</strong>
```

Change the voice-room option loop to expose its index and render:

```vue
<option
  v-for="(device, index) in devices"
  :key="device.deviceId"
  :value="device.deviceId"
>
  {{ displayMicrophoneLabel(device.label, index) }}
</option>
```

- [ ] **Step 4: Run both component suites and verify GREEN**

Run the Step 2 command. Expected: all device-check and voice-room tests pass.

- [ ] **Step 5: Commit participant device-label rendering**

```powershell
git add frontend/src/study1/components/Study1DeviceCheck.vue frontend/src/study1/components/Study1DeviceCheck.spec.js frontend/src/study1/components/Study1VoiceRoom.vue frontend/src/study1/components/Study1VoiceRoom.spec.js
git commit -m "feat: keep Study 1 device labels English"
```

### Task 5: Enforce English-only Study 1 source and verify the built UI

**Files:**
- Create: `frontend/src/study1/englishOnly.spec.js`

- [ ] **Step 1: Add the source-tree regression test**

```js
import { readdirSync, readFileSync } from 'node:fs'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, it } from 'vitest'

const ROOT = fileURLToPath(new URL('.', import.meta.url))
const CJK_PATTERN = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/u

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(path)
    const isApplicationSource = ['.js', '.vue'].includes(extname(entry.name))
      && !entry.name.endsWith('.spec.js')
    return isApplicationSource ? [path] : []
  })
}

it('contains no CJK application copy in the Study 1 source tree', () => {
  const offenders = sourceFiles(ROOT).filter(path => CJK_PATTERN.test(readFileSync(path, 'utf8')))
  expect(offenders).toEqual([])
})
```

- [ ] **Step 2: Run the full frontend verification**

```powershell
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Expected: all tests pass and Vite production build exits 0.

- [ ] **Step 3: Rebuild only the Docker frontend with the local proxy**

```powershell
docker compose build `
  --build-arg HTTP_PROXY=http://host.docker.internal:7897 `
  --build-arg HTTPS_PROXY=http://host.docker.internal:7897 `
  frontend
docker compose up -d --no-deps --force-recreate frontend
```

Expected: `humanagent-frontend` is running on port 8080.

- [ ] **Step 4: Verify desktop and narrow layouts in a real browser**

At `http://localhost:8080/researcher/study1`:

- desktop computed inline margins for `.login-centered` are equal;
- at 390 px viewport width, the card stays within the viewport;
- the custom uploaders display only English text;
- injected Chinese microphone labels render as `Microphone 1` in device check,
  voice-room selection, and researcher media status.

- [ ] **Step 5: Run final repository checks and commit**

```powershell
git diff --check
git status --short
git add frontend/src/study1/englishOnly.spec.js docs/superpowers/plans/2026-07-27-study1-english-ui.md
git commit -m "test: enforce English-only Study 1 UI"
```

- [ ] **Step 6: Push the existing PR branch**

```powershell
git push origin codex/study1-media-service
```

Expected: PR #1 updates without merging into `main`.
