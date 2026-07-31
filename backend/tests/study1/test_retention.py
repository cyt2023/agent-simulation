import pytest


class FakeMediaGateway:
    mode = "fake"

    def __init__(self):
        self.commands = []

    def send_command(self, envelope):
        self.commands.append(envelope)
        return {"accepted": True, "duplicate": False, "command_id": envelope["command_id"]}


def test_retention_requires_dry_run_then_checksum_approval():
    from study1.retention_service import InMemoryRetentionStore, RetentionError, RetentionService

    retention = RetentionService(store=InMemoryRetentionStore())
    job = retention.create_dry_run("session-1", requested_by="privacy-admin")

    with pytest.raises(RetentionError) as error:
        retention.execute(
            job.job_id,
            approved_manifest_checksum="wrong",
            approved_by="privacy-admin",
            reason="Participant withdrawal",
        )

    assert error.value.code == "RETENTION_CHECKSUM_MISMATCH"
    assert retention.get_job(job.job_id).status == "dry_run"


def test_retention_execute_sends_purge_command_and_keeps_non_identifying_tombstone():
    from study1.retention_service import InMemoryRetentionStore, RetentionService

    gateway = FakeMediaGateway()
    retention = RetentionService(store=InMemoryRetentionStore(), media_gateway=gateway)
    job = retention.create_dry_run(
        "session-1",
        requested_by="privacy-admin",
        subject_pseudo_ids=["pseudo-1"],
    )

    executed = retention.execute(
        job.job_id,
        approved_manifest_checksum=job.manifest_checksum,
        approved_by="second-admin",
        reason="Participant withdrawal",
    )

    assert executed.status == "executed"
    assert gateway.commands[0]["command"] == "PURGE_SESSION_MEDIA"
    assert gateway.commands[0]["payload"]["retention_job_id"] == job.job_id
    tombstone = retention.tombstones("session-1")[0]
    assert tombstone.session_id == "session-1"
    assert "pseudo-1" not in repr(tombstone)


def test_privacy_admin_can_create_and_execute_retention_job_routes(study1_client, token_manager):
    from study1.privacy_routes import set_retention_service_for_testing
    from study1.retention_service import InMemoryRetentionStore, RetentionService

    gateway = FakeMediaGateway()
    set_retention_service_for_testing(
        RetentionService(store=InMemoryRetentionStore(), media_gateway=gateway)
    )
    headers = {
        "Authorization": "Bearer "
        + token_manager.issue_researcher(["privacy_admin", "operate"])
    }
    try:
        created = study1_client.post(
            "/api/study1/privacy/retention-jobs",
            headers=headers,
            json={
                "session_id": "session-1",
                "subject_pseudo_ids": ["pseudo-1"],
            },
        )
        assert created.status_code == 201
        payload = created.get_json()

        executed = study1_client.post(
            f"/api/study1/privacy/retention-jobs/{payload['job_id']}/execute",
            headers=headers,
            json={
                "approved_manifest_checksum": payload["manifest_checksum"],
                "reason": "Participant withdrawal",
            },
        )

        assert executed.status_code == 200
        assert executed.get_json()["status"] == "executed"
        assert gateway.commands[0]["command"] == "PURGE_SESSION_MEDIA"
    finally:
        set_retention_service_for_testing(None)
