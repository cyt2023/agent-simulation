from __future__ import annotations

import pytest

from study1.action_policy import ActionPolicyViolation, authorize_action


def test_paused_session_rejects_runtime_operations():
    session = {"status": "paused", "phase": "SYNC_MEETING"}
    for action, role in (
        ("submit", "principal"),
        ("advance", "researcher"),
        ("issue_media_access", "teammate_1"),
    ):
        with pytest.raises(ActionPolicyViolation) as error:
            authorize_action(session, action, role)
        assert error.value.code == "SESSION_PAUSED"


def test_material_read_is_phase_and_role_gated():
    session = {"status": "running", "phase": "PROXY_CONFIGURATION"}
    authorize_action(session, "material_read", "principal")
    with pytest.raises(ActionPolicyViolation) as error:
        authorize_action(session, "material_read", "teammate_1")
    assert error.value.code == "MATERIAL_ACCESS_NOT_AVAILABLE"
