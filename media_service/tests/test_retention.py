from datetime import datetime, timezone

import pytest

from media_service.app.commands import CommandService
from media_service.app.schemas import CommandEnvelope


@pytest.mark.asyncio
async def test_purge_command_dispatches_to_runtime(repository):
    class Runtime:
        def __init__(self):
            self.purges = []

        async def purge_session_media(self, session_id, phase_version, payload):
            self.purges.append((session_id, phase_version, payload))

    runtime = Runtime()
    service = CommandService(repository, runtime)
    envelope = CommandEnvelope(
        command_id="purge-command-1",
        session_id="session-1",
        phase_version=9,
        command="PURGE_SESSION_MEDIA",
        issued_at=datetime.now(timezone.utc),
        payload={
            "retention_job_id": "job-1",
            "manifest_checksum": "abc123",
            "reason": "Participant withdrawal",
        },
    )

    accepted = service.accept(envelope)
    await service.execute(accepted.command_id)

    assert runtime.purges == [("session-1", 9, envelope.payload)]


def test_repository_purge_removes_session_media_and_keeps_tombstone(repository):
    repository.add_transcript_segment(
        segment_id="seg-1",
        session_id="session-1",
        runtime_id="runtime-1",
        speaker="teammate_1",
        start_ms=0,
        end_ms=1000,
        text="Sensitive discussion text",
        confidence=0.99,
        is_final=True,
        provider_version="mock-asr",
    )
    repository.create_artifact(
        artifact_id="artifact-1",
        session_id="session-1",
        kind="summary",
        version="1",
        content="Sensitive summary text",
        storage_uri=None,
        checksum="checksum",
        generator_version="mock",
        metadata={},
    )

    tombstone = repository.purge_session_media(
        "session-1",
        retention_job_id="job-1",
        manifest_checksum="abc123",
        reason="Participant withdrawal",
    )

    assert repository.list_session_segments("session-1") == []
    assert repository.list_session_artifacts("session-1") == []
    assert tombstone.session_id == "session-1"
    assert tombstone.purged_counts["transcript_segments"] == 1
    assert any(
        row.event_type == "MEDIA_PURGED"
        for row in repository.list_session_outbox("session-1")
    )
