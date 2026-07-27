# Study 1 Centered and English-Only UI Design

## Goal

Make the newly added Study 1 researcher and participant interfaces consistently
English-only, while centering the researcher sign-in card within the page content.
The legacy platform routes and interfaces remain unchanged.

## Scope

Included:

- `frontend/src/study1/views/Study1Researcher.vue`
- `frontend/src/study1/views/Study1Participant.vue`
- Study 1 components and UI-only helpers under `frontend/src/study1/`
- Study 1 frontend tests

Excluded:

- Legacy `/login`, `/participant`, and `/researcher` interfaces
- Browser chrome, browser permission prompts, and operating-system dialogs
- Stored source device labels and exported research data
- Backend API contracts and experiment-state behavior

## Layout

The unauthenticated researcher page keeps its existing title and visual style.
The sign-in card receives a fixed responsive maximum width and automatic inline
margins so it is horizontally centered at desktop and mobile widths. Its fields,
button, validation behavior, and authentication flow remain unchanged.

## English-Only Application UI

### File selection

Native file inputs are visually hidden because their visible button and status
text follow the host operating-system language. Each Study 1 material uploader
uses an accessible custom English control with these states:

- `Choose files`
- `No files selected`
- `1 file selected`
- `<N> files selected`

The hidden input remains keyboard accessible through its associated label and
continues to accept the existing PDF, TXT, and Markdown file types.

### Device labels

Microphone labels originate from the operating system and may contain Chinese.
Study 1 retains the original label for device selection, API reporting, and data
capture, but passes it through a UI formatter before rendering. Labels containing
CJK characters are displayed as stable English fallbacks such as `Microphone 1`.
Existing English labels remain visible. The formatter is used in:

- the participant device check;
- microphone options in the voice room;
- the researcher media-participant table.

The device ID remains the selection key, so changing the displayed label does not
change which microphone is used.

### Static copy

All static Study 1 strings remain English. A source scan covers `.vue` and `.js`
files under `frontend/src/study1` to prevent accidental CJK application copy.

## Accessibility and Responsive Behavior

- The custom upload control is associated with the hidden file input.
- Focus remains visible for keyboard users.
- File-selection status is exposed as readable English text.
- The centered sign-in card does not exceed the available mobile viewport width.
- Existing form semantics and button disabled states are preserved.

## Testing

Automated tests cover:

1. CJK device labels render as English fallbacks while English labels are kept.
2. File upload controls expose only English visible text and correctly report
   zero, one, and multiple selected files.
3. The researcher sign-in card has the dedicated centered layout class.
4. The Study 1 source tree contains no CJK application strings.
5. The existing Study 1 component tests and frontend production build still pass.

Browser verification uses the Docker frontend at
`http://localhost:8080/researcher/study1` and checks desktop and narrow viewport
layouts. It also visits participant device and meeting states to confirm that raw
Chinese operating-system device labels are not rendered by the application.

## Acceptance Criteria

- The researcher sign-in card is horizontally centered.
- No Study 1 application surface renders Chinese file-picker or device-label text.
- All Study 1-authored copy is English.
- Legacy platform pages are untouched.
- Device selection, material upload, authentication, and experiment flow continue
  to behave as before.
