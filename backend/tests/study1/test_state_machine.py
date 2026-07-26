from datetime import datetime, timezone

import pytest

from study1.models import PHASE_ORDER, Study1Phase, Study1Role
from study1.state_machine import (
    InvalidTransition,
    OverrideReasonRequired,
    PrerequisitesNotMet,
    can_transition,
    readiness,
    transition_phase,
)


ACTOR = {"participant_id": "researcher-1", "role": Study1Role.RESEARCHER.value}
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def make_session(phase=Study1Phase.SETUP, completion=None):
    return {
        "session_id": "session-1",
        "phase": phase.value,
        "phase_version": 1,
        "phase_started_at": "2026-01-01T00:00:00Z",
        "phase_history": [
            {
                "phase": phase.value,
                "phase_version": 1,
                "phase_started_at": "2026-01-01T00:00:00Z",
                "phase_ended_at": None,
            }
        ],
        "completion": completion or {},
    }


def test_phase_order_matches_protocol():
    assert PHASE_ORDER[0] is Study1Phase.SETUP
    assert PHASE_ORDER[-1] is Study1Phase.COMPLETED
    assert len(PHASE_ORDER) == 15


def test_setup_can_only_advance_to_material_reading():
    session = make_session()
    assert can_transition(session, Study1Phase.MATERIAL_READING)
    assert not can_transition(session, Study1Phase.PRE_VOTE)
    with pytest.raises(InvalidTransition):
        transition_phase(session, Study1Phase.PRE_VOTE, ACTOR)


def test_material_reading_requires_all_three_acknowledgements():
    session = make_session(
        Study1Phase.MATERIAL_READING,
        {
            "material_ack:principal": True,
            "material_ack:teammate_1": True,
        },
    )
    check = can_transition(session, Study1Phase.PRE_VOTE)
    assert not check
    assert check.missing == ("material_ack:teammate_2",)
    with pytest.raises(PrerequisitesNotMet) as error:
        transition_phase(session, Study1Phase.PRE_VOTE, ACTOR)
    assert error.value.missing == ("material_ack:teammate_2",)


def test_transition_updates_version_history_and_utc_timestamp():
    session = make_session()
    event = transition_phase(
        session, Study1Phase.MATERIAL_READING, ACTOR, reason="start", now=NOW
    )
    assert session["phase"] == "MATERIAL_READING"
    assert session["phase_version"] == 2
    assert session["phase_history"][0]["phase_ended_at"] == "2026-01-02T03:04:05Z"
    assert event["from_phase"] == "SETUP"
    assert event["to_phase"] == "MATERIAL_READING"
    assert event["entered_by"]["role"] == "researcher"


def test_force_advance_requires_reason_and_records_missing_prerequisites():
    session = make_session(Study1Phase.MATERIAL_READING)
    with pytest.raises(OverrideReasonRequired):
        transition_phase(
            session, Study1Phase.PRE_VOTE, ACTOR, override=True, reason=" "
        )
    event = transition_phase(
        session,
        Study1Phase.PRE_VOTE,
        ACTOR,
        override=True,
        reason="Participant withdrew",
    )
    assert event["override"] is True
    assert event["transition_reason"] == "Participant withdrew"
    assert set(event["prerequisites"]["missing"]) == {
        "material_ack:principal",
        "material_ack:teammate_1",
        "material_ack:teammate_2",
    }


def test_readiness_does_not_mutate_or_auto_advance():
    session = make_session()
    result = readiness(session)
    assert result == {
        "ready_to_advance": True,
        "next_phase": "MATERIAL_READING",
        "missing_prerequisites": [],
    }
    assert session["phase"] == "SETUP"
