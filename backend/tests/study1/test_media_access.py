from __future__ import annotations

import pytest

from study1.models import Study1Phase, Study1Role
from study1.services import InMemoryStudy1Repository, Study1Service, Study1ServiceError


RESEARCHER = {
    "participant_id": "researcher",
    "role": "researcher",
    "session_id": None,
}


class CapturingGateway:
    mode = "http"

    def __init__(self):
        self.commands = []
        self.access_requests = []
        self.device_reports = []

    def send_command(self, envelope):
        self.commands.append(envelope)
        return {
            "accepted": True,
            "duplicate": False,
            "command_id": envelope["command_id"],
            "runtime_state": "PREPARING",
        }

    def issue_access(self, payload):
        self.access_requests.append(payload)
        return {"room_name": "room", "token": "rtc-token", "url": "ws://livekit"}

    def get_status(self, session_id):
        return {"session_id": session_id, "service_status": "ok"}

    def export_bundle(self, session_id):
        return None

    def get_recording(self, session_id, recording_id, range_header=None):
        self.recording_request = (session_id, recording_id, range_header)
        return type(
            "RecordingResponse",
            (),
            {
                "content": b"audio-range",
                "status_code": 206,
                "headers": {
                    "Content-Type": "audio/wav",
                    "Content-Range": "bytes 0-10/100",
                    "Accept-Ranges": "bytes",
                },
            },
        )()

    def report_device(self, payload):
        self.device_reports.append(payload)
        return {"accepted": True, "connection_id": "connection-1"}


def _service_with_proxy_data(token_manager):
    gateway = CapturingGateway()
    repository = InMemoryStudy1Repository()
    service = Study1Service(repository, token_manager, gateway)
    created = service.create_session(
        "authorized-context",
        materials_by_role={
            "principal": [{"title": "P evidence", "content": "P-authorized fact"}],
            "teammate_1": [{"title": "T1 secret", "content": "private T1 fact"}],
            "teammate_2": [{"title": "T2 secret", "content": "private T2 fact"}],
        },
    )
    session_id = created["session"]["session_id"]
    repository.sessions[session_id]["phase"] = Study1Phase.PROXY_MEETING.value
    repository.sessions[session_id]["phase_version"] = 5
    principal = next(
        participant
        for participant in repository.sessions[session_id]["participants"]
        if participant["role"] == Study1Role.PRINCIPAL.value
    )
    repository.submissions.append(
        {
            "submission_id": "proxy-config-1",
            "session_id": session_id,
            "participant_id": principal["participant_id"],
            "role": "principal",
            "submission_type": "proxy_config",
            "payload": {
                "priorities": "support option A",
                "boundaries": "do not decide for P",
                "authorization_confirmed": True,
                "authorized_material_ids": [
                    next(
                        item["material_id"]
                        for item in repository.materials
                        if item["session_id"] == session_id
                        and item["role"] == "principal"
                    )
                ],
            },
            "locked": True,
            "previous_submission_id": None,
        }
    )
    return service, gateway, session_id, principal


def test_start_proxy_context_is_built_by_a(token_manager):
    service, gateway, session_id, _principal = _service_with_proxy_data(token_manager)

    service.issue_media_command(
        session_id,
        RESEARCHER,
        "START_PROXY_MEETING",
        payload={"materials": [{"content": "injected T1 secret"}]},
    )

    context = gateway.commands[0]["payload"]["authorized_context"]
    assert context["proxy_config_submission_id"] == "proxy-config-1"
    assert context["proxy_config"] == {
        "priorities": "support option A",
        "boundaries": "do not decide for P",
        "authorization_confirmed": True,
        "authorized_material_ids": [context["materials"][0]["material_id"]],
    }
    assert [item["title"] for item in context["materials"]] == ["P evidence"]
    assert "private T1 fact" not in str(context)
    assert "injected T1 secret" not in str(context)


def test_proxy_config_requires_explicit_authorization_of_principal_materials(token_manager):
    repository = InMemoryStudy1Repository()
    service = Study1Service(repository, token_manager, CapturingGateway())
    created = service.create_session(
        "authorization-validation",
        materials_by_role={
            "principal": [{"title": "P evidence", "content": "P fact"}],
            "teammate_1": [{"title": "T1 secret", "content": "T1 fact"}],
        },
    )
    session_id = created["session"]["session_id"]
    repository.sessions[session_id]["phase"] = Study1Phase.PROXY_CONFIGURATION.value
    principal = next(
        participant
        for participant in repository.sessions[session_id]["participants"]
        if participant["role"] == Study1Role.PRINCIPAL.value
    )
    t1_material_id = next(
        item["material_id"]
        for item in repository.materials
        if item["session_id"] == session_id and item["role"] == "teammate_1"
    )

    with pytest.raises(Study1ServiceError) as missing_confirmation:
        service.submit(
            session_id,
            principal,
            "proxy_config",
            "1.0",
            {"priorities": "preserve cost", "authorized_material_ids": []},
        )
    assert missing_confirmation.value.code == "PROXY_AUTHORIZATION_REQUIRED"

    with pytest.raises(Study1ServiceError) as foreign_material:
        service.submit(
            session_id,
            principal,
            "proxy_config",
            "1.0",
            {
                "priorities": "preserve cost",
                "authorization_confirmed": True,
                "authorized_material_ids": [t1_material_id],
            },
        )
    assert foreign_material.value.code == "INVALID_PROXY_MATERIAL_AUTHORIZATION"


def test_failed_a_to_b_delivery_can_retry_same_command_id(token_manager):
    class FailOnceGateway(CapturingGateway):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        def send_command(self, envelope):
            from study1.media_gateway import MediaGatewayError

            self.attempts += 1
            if self.attempts == 1:
                raise MediaGatewayError("temporary outage")
            return super().send_command(envelope)

    gateway = FailOnceGateway()
    repository = InMemoryStudy1Repository()
    service = Study1Service(repository, token_manager, gateway)
    session_id = service.create_session("retry")["session"]["session_id"]
    repository.sessions[session_id]["phase"] = Study1Phase.PROXY_MEETING.value
    repository.sessions[session_id]["phase_version"] = 5
    command_id = "retry-command-1"

    with pytest.raises(Study1ServiceError) as unavailable:
        service.issue_media_command(
            session_id, RESEARCHER, "END_CURRENT_MEETING", command_id=command_id
        )
    assert unavailable.value.code == "MEDIA_SERVICE_UNAVAILABLE"

    result = service.issue_media_command(
        session_id, RESEARCHER, "END_CURRENT_MEETING", command_id=command_id
    )

    assert gateway.attempts == 2
    assert result["duplicate"] is True
    assert len(
        [event for event in repository.events if event["event_type"] == "media_command"]
    ) == 1


def test_principal_cannot_receive_proxy_room_access(token_manager):
    service, gateway, session_id, principal = _service_with_proxy_data(token_manager)
    identity = {**principal, "session_id": session_id}

    try:
        service.issue_media_access(session_id, identity)
    except Exception as error:
        assert getattr(error, "code", None) == "MEDIA_ACCESS_FORBIDDEN"
    else:
        raise AssertionError("principal unexpectedly received Proxy room access")
    assert gateway.access_requests == []


def test_teammate_access_uses_authoritative_phase_and_role(token_manager):
    service, gateway, session_id, _principal = _service_with_proxy_data(token_manager)
    teammate = next(
        participant
        for participant in service.repository.sessions[session_id]["participants"]
        if participant["role"] == "teammate_1"
    )
    result = service.issue_media_access(
        session_id, {**teammate, "session_id": session_id}
    )

    assert result["token"] == "rtc-token"
    assert gateway.access_requests == [
        {
            "session_id": session_id,
            "phase": "PROXY_MEETING",
            "phase_version": 5,
            "role": "teammate_1",
            "participant_id": teammate["participant_id"],
        }
    ]


def test_recording_replay_requires_principal_review_access(token_manager):
    service, gateway, session_id, principal = _service_with_proxy_data(token_manager)
    identity = {**principal, "session_id": session_id}

    try:
        service.get_recording(session_id, identity, "teammate_1.wav", "bytes=0-10")
    except Exception as error:
        assert getattr(error, "code", None) == "MEDIA_REPLAY_FORBIDDEN"
    else:
        raise AssertionError("recording was available before Review")

    service.repository.sessions[session_id]["phase"] = Study1Phase.REVIEW.value
    service.repository.sessions[session_id]["completion"][
        "delegation_expectation:principal"
    ] = True
    response = service.get_recording(
        session_id, identity, "teammate_1.wav", "bytes=0-10"
    )
    assert response.content == b"audio-range"
    assert gateway.recording_request == (
        session_id,
        "teammate_1.wav",
        "bytes=0-10",
    )


def test_device_report_uses_signed_identity_not_body_role(token_manager):
    service, gateway, session_id, principal = _service_with_proxy_data(token_manager)
    service.repository.sessions[session_id]["phase"] = Study1Phase.SETUP.value
    service.repository.sessions[session_id]["phase_version"] = 1

    result = service.report_media_device(
        session_id,
        {**principal, "session_id": session_id},
        {
            "role": "researcher",
            "state": "ready",
            "device": {"kind": "audioinput", "label": "USB microphone"},
        },
    )

    assert result["accepted"] is True
    assert gateway.device_reports == [
        {
            "session_id": session_id,
            "phase_version": 1,
            "participant_id": principal["participant_id"],
            "role": "principal",
            "state": "ready",
            "device": {"kind": "audioinput", "label": "USB microphone"},
        }
    ]
