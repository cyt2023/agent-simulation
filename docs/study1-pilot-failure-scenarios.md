# Study 1 Pilot Failure Scenarios

This catalog is used by `scripts/run_study1_synthetic_audio_pilot.py`.

| Scenario | Injected fault | Expected observation |
| --- | --- | --- |
| reconnect | Drop the link and reconnect once | The same participant identity reconnects without duplication. |
| microphone_denial | Deny microphone permission | The UI stays neutral and explains the local device issue. |
| barge_in | Interrupt active proxy playback | The current proxy utterance stops once and logs the interruption. |
| handoff | Return the principal to the room | Proxy speaking rights stop and the sync phase can begin. |
| summary_retry | Force a summary retry | The retry reuses the frozen configuration and records the reason. |
| transcript_correction | Submit a transcript correction | The original transcript remains visible in the audit trail. |
| export | Request the final export | The bundle contains media, transcript, summary, and integrity artifacts. |
