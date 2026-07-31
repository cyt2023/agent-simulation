from __future__ import annotations

from study1.models import Study1Phase


class RecordingGateway:
    def get_recording(self, session_id, recording_id, range_header=None):
        self.recording_request = (session_id, recording_id, range_header)
        return type(
            "RecordingResponse",
            (),
            {
                "content": b"audio",
                "status_code": 206,
                "headers": {
                    "Content-Type": "audio/wav",
                    "Content-Range": "bytes 0-4/5",
                    "Accept-Ranges": "bytes",
                },
            },
        )()

    def get_status(self, session_id):
        return {"session_id": session_id, "service_status": "ok"}

    def export_bundle(self, session_id):
        return None


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Range": "bytes=0-4"}


def test_raw_media_requires_researcher_read_raw_media_scope(
    study1_client, memory_service, token_manager
):
    gateway = RecordingGateway()
    memory_service.media_gateway = gateway
    created = memory_service.create_session("scoped raw media")
    session_id = created["session"]["session_id"]
    memory_service.repository.sessions[session_id]["phase"] = Study1Phase.REVIEW.value
    operator_token = token_manager.issue_researcher(scopes=["operate"])

    response = study1_client.get(
        f"/api/study1/sessions/{session_id}/recordings/proxy.wav",
        headers=_headers(operator_token),
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "RESEARCHER_SCOPE_REQUIRED"


def test_researcher_with_read_raw_media_scope_can_stream_recording(
    study1_client, memory_service, token_manager
):
    gateway = RecordingGateway()
    memory_service.media_gateway = gateway
    created = memory_service.create_session("scoped raw media")
    session_id = created["session"]["session_id"]
    memory_service.repository.sessions[session_id]["phase"] = Study1Phase.REVIEW.value
    auditor_token = token_manager.issue_researcher(
        scopes=["operate", "read_raw_media"]
    )

    response = study1_client.get(
        f"/api/study1/sessions/{session_id}/recordings/proxy.wav",
        headers=_headers(auditor_token),
    )

    assert response.status_code == 206
    assert response.data == b"audio"
    assert gateway.recording_request == (session_id, "proxy.wav", "bytes=0-4")
