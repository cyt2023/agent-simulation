# Study 1 Ten-Run Stress Test Template

Use this template for the ten-run stress pass before formal pilot work.

Runner:

`python scripts/run_study1_synthetic_audio_pilot.py --template stress --output-dir output/pilots/stress-01`

| Run | Scenario | Result | Notes |
| --- | --- | --- | --- |
| 1 | reconnect |  |  |
| 2 | microphone_denial |  |  |
| 3 | barge_in |  |  |
| 4 | handoff |  |  |
| 5 | summary_retry |  |  |
| 6 | transcript_correction |  |  |
| 7 | reconnect |  |  |
| 8 | barge_in |  |  |
| 9 | handoff |  |  |
| 10 | export |  |  |

Record the release id, bundle checksum, and any recovery notes below the table.
