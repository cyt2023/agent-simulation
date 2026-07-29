# Study 1 Audio-Only Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all approved Study 1 gaps with an audio-only meeting system, an English-only interface, reconstructable research data, and formal technical acceptance tooling.

**Architecture:** Platform A remains the sole experiment authority, Media Service B remains an internal audio participant and artifact producer, and the frontend consumes server capabilities rather than inferring permissions. Work is split into four dependency-aware plans so platform, media, and frontend work can proceed independently before data/export integration.

**Tech Stack:** Flask, SQLAlchemy, PostgreSQL, FastAPI, LiveKit, Python asyncio, Vue 3, Vite, Vitest, Playwright, Docker Compose.

---

## Execution Order

1. [Platform protocol plan](./2026-07-29-study1-platform-protocol.md)
2. [Audio runtime plan](./2026-07-29-study1-audio-runtime.md), may run in parallel with plan 1
3. [English meeting and workflow UI plan](./2026-07-29-study1-english-workflow-ui.md), may start against the frozen contracts from plans 1 and 2
4. [Research data, privacy, and acceptance plan](./2026-07-29-study1-research-data-acceptance.md), begins after platform schema contracts are stable

## Integration Gates

- [ ] Gate A: Platform protocol tests pass and formal Session DTOs expose canonical capabilities.
- [ ] Gate B: Media tests prove stable-room handoff, neutral failure, full Agent audit, and aligned audio artifacts.
- [ ] Gate C: Frontend tests and Playwright screenshots prove the reference layout, responsive behavior, and English-only output.
- [ ] Gate D: Full export reconstruction, Study 2 read-only contracts, privacy lifecycle, release verification, and end-to-end flow pass.
- [ ] Final gate: run all backend, media, frontend, build, Compose, contract, and Playwright checks from a clean process state.

## Approved Gap Coverage

| Gap | Owning plan/task |
|---|---|
| 1. Task and Hidden Profile model | Platform tasks 1-2 |
| 2. Session freeze | Platform task 3 |
| 3. Real pause behavior | Platform task 4 |
| 4. Phase-gated materials | Platform task 4 |
| 5. Candidate-based initial judgment | Platform task 5, UI task 4 |
| 6. Team and individual final decisions | Platform tasks 5-7, UI task 4 |
| 7. Shared follow-up | Platform tasks 6-7, UI task 4 |
| 8. Proxy confirmation and fixed authority | Platform task 3, UI task 4 |
| 9. Proxy audit and recovery | Audio tasks 1, 4-5 |
| 10. Proxy identity | Audio task 5, UI task 3 |
| 11. Video scope | Explicitly excluded and guarded by UI/media tests |
| 12. Stable handoff | Audio tasks 2-3, UI task 2 |
| 13. RTC pipeline and quality | Audio tasks 4-8, data task 6 |
| 14. Summary and Review | Data tasks 3-4, UI tasks 5-6 |
| 15. Exact formal instruments | Platform task 5, UI task 4 |
| 16. Markers and replay | Data task 5, UI tasks 5-6 |
| 17. Unified timeline and export | Audio task 7, data task 7 |
| 18. Study 2 interfaces | Data task 8 |
| 19. Privacy and formal acceptance | Data tasks 1-2 and 9 |

## Commit Policy

Each task follows red-green-refactor and ends with a scoped commit. Do not mix unrelated modules in one commit. Never add the existing untracked `Agent Simulation/`, `output/`, `personal-site-install-test/`, or `tmp/` directories.
