# Study 1 Release Freeze

This document defines the technical freeze for Study 1. A frozen release is a
specific pairing of Platform A, Media Service B, protocol configuration, task
materials, instruments, prompts, provider settings, and data export schemas.

## Freeze Steps

1. Build and test the target branch.
2. Generate the release manifest:

   ```powershell
   python scripts/build_study1_release_manifest.py `
     --output release/study1-release-manifest.json `
     --backend-build <backend-build-id> `
     --frontend-build <frontend-build-id> `
     --media-build <media-build-id>
   ```

3. Verify the manifest:

   ```powershell
   python scripts/verify_study1_release.py release/study1-release-manifest.json
   ```

4. Set the same release identity on A and B:

   ```dotenv
   STUDY1_RELEASE_ID=<manifest release_id>
   STUDY1_RELEASE_CHECKSUM=<manifest checksum>
   ```

   Media Service B also reads `STUDY1_RELEASE_ID` and
   `STUDY1_RELEASE_CHECKSUM`. If B is configured with these values, incoming A
   commands must include matching values or B returns `409`.

5. Run the automated acceptance gates from the manifest.
6. Complete the external signoffs listed below before any real data collection.

## External Signoffs

Automation can only establish technical acceptance. The release must not be
described as data-collection-ready until all of these are complete and recorded:

- IRB or ethics approval for the exact consent text and study procedure.
- Production WSS/TURN and network configuration validated on real devices.
- Production ASR, LLM, TTS, LiveKit, database, and storage credentials installed.
- Real participant pilot runs completed and reviewed.

## Drift Rules

- Build IDs must not be `unknown`, `unset`, or `latest`.
- Prompt, model, task, facts, instrument, consent, marker, replay, retention, and
  Study 2 contract versions are part of the manifest checksum.
- A and B must use the same `release_id` and `checksum`.
- If any release value changes, generate a new manifest and repeat acceptance.
