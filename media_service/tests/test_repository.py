from media_service.app.schemas import CommandEnvelope


def test_command_id_and_semantic_key_are_idempotent(repository, command_payload):
    command = CommandEnvelope.model_validate(command_payload)
    semantic_key = (
        f"{command.session_id}:{command.phase_version}:{command.command.value}"
    )

    first = repository.accept_command(command, semantic_key)
    replay = repository.accept_command(command, semantic_key)
    same_effect = repository.accept_command(
        command.model_copy(update={"command_id": "other-id"}), semantic_key
    )

    assert first.duplicate is False
    assert replay.duplicate is True
    assert same_effect.duplicate is True
    assert same_effect.command_id == first.command_id


def test_outbox_retry_state_survives_repository_calls(repository):
    message = repository.enqueue_event(
        session_id="session-1",
        phase_version=3,
        event_type="MEDIA_READY",
        payload={"room_kind": "proxy"},
    )
    repository.mark_outbox_attempt(message.event_id, "temporary failure")

    pending = repository.pending_outbox()
    assert len(pending) == 1
    assert pending[0].event_id == message.event_id
    assert pending[0].attempt_count == 1
    assert pending[0].last_error == "temporary failure"
