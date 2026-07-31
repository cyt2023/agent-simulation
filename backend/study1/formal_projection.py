"""Formal Study 1 projection helpers.

These helpers derive canonical readiness/capability views from persisted
records while keeping the legacy append-only payloads intact.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Mapping

from .action_policy import capabilities_for
from .models import HUMAN_ROLES, PHASE_ORDER, Study1Phase, Study1Role

REVIEW_UI_EVENT_TYPES = {
    "review_page_enter",
    "review_page_leave",
    "summary_visible",
    "transcript_expand",
    "transcript_collapse",
    "transcript_segment_view",
    "scroll_depth",
    "active_reading_time",
    "critical_marker",
    "recording_replay",
    "rtc_metric_sample",
}


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        except ValueError:
            return None
    return None


def project_formal_completion(
    session: Mapping[str, Any], data: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    if session.get("protocol_mode") != "formal_v2":
        return copy.deepcopy(session.get("completion") or {})

    exported = data or {}
    completion: dict[str, Any] = {}

    for submission in exported.get("submissions") or []:
        if submission.get("previous_submission_id") is not None:
            continue
        submission_type = str(submission.get("submission_type") or "")
        role = str(submission.get("role") or "")
        if submission_type in {
            "consent",
            "material_ack",
            "proxy_config",
            "proxy_ready",
            "delegation_expectation",
            "comprehension_measurement",
            "post_survey",
        }:
            completion[f"{submission_type}:{role}"] = True
        elif submission_type in {
            "pre_vote",
            "tentative_decision",
            "final_decision",
            "followup_task",
        }:
            completion[f"{submission_type}:{role}"] = True
            canonical = {
                "pre_vote": "pre_individual",
                "tentative_decision": "tentative_individual",
                "final_decision": "final_individual",
                "followup_task": "followup_task",
            }[submission_type]
            completion[f"{canonical}:{role}"] = True

    for decision in exported.get("decisions") or []:
        if not decision.get("locked", True):
            continue
        kind = str(decision.get("decision_kind") or "")
        role = str(decision.get("role") or "")
        if kind in {"pre_individual", "tentative_individual", "final_individual"}:
            completion[f"{kind}:{role}"] = True
            alias = {
                "pre_individual": "pre_vote",
                "tentative_individual": "tentative_decision",
                "final_individual": "final_decision",
            }[kind]
            completion[f"{alias}:{role}"] = True
        elif kind == "team_final":
            completion["team_final_locked"] = True

    for artifact in exported.get("shared_artifacts") or []:
        kind = str(artifact.get("kind") or "")
        if kind == "team_final" and artifact.get("locked_revision_id"):
            completion["team_final_locked"] = True
        elif kind == "followup_task" and artifact.get("locked_revision_id"):
            completion["followup_task_locked"] = True

    if completion.get("team_final_locked") or all(
        completion.get(f"final_individual:{role.value}") for role in HUMAN_ROLES
    ):
        completion["team_final_locked"] = True

    if completion.get("followup_task_locked") or all(
        completion.get(f"followup_task:{role.value}") for role in HUMAN_ROLES
    ):
        completion["followup_task_locked"] = True
        for role in HUMAN_ROLES:
            completion[f"followup_task:{role.value}"] = True

    for event in exported.get("events") or []:
        event_type = str(event.get("event_type") or "")
        payload = event.get("payload") or {}
        if event_type == "ui_event":
            ui_event_type = str(payload.get("ui_event_type") or "")
            if ui_event_type not in REVIEW_UI_EVENT_TYPES:
                continue
            if event.get("role") == Study1Role.PRINCIPAL.value:
                completion["review_reading_recorded:principal"] = True
                if ui_event_type == "review_page_enter":
                    completion["review_opened:principal"] = True
        elif event_type == "media_event":
            media_type = str(payload.get("event_type") or "")
            if media_type == "HANDOFF_COMPLETE":
                completion["handoff_complete"] = True
            elif media_type == "MEETING_ENDED":
                if event.get("phase") == Study1Phase.PROXY_MEETING.value:
                    completion["proxy_meeting_ended"] = True
                elif event.get("phase") == Study1Phase.SYNC_MEETING.value:
                    completion["sync_meeting_ended"] = True

    opened_at = _dt(session.get("review_opened_at"))
    if opened_at and completion.get("review_reading_recorded:principal"):
        minimum = int(session.get("minimum_review_seconds") or 0)
        if minimum <= 0:
            completion["minimum_review_time_met:principal"] = True
        else:
            review_events = [
                _dt(event.get("occurred_at"))
                for event in exported.get("events") or []
                if event.get("event_type") == "ui_event"
                and event.get("role") == Study1Role.PRINCIPAL.value
                and str((event.get("payload") or {}).get("ui_event_type") or "")
                in REVIEW_UI_EVENT_TYPES
            ]
            if any(
                occurred is not None
                and int((occurred - opened_at).total_seconds()) >= minimum
                for occurred in review_events
            ):
                completion["minimum_review_time_met:principal"] = True

    for artifact in exported.get("artifacts") or []:
        if str(artifact.get("type") or "") == "summary":
            completion["summary_artifact_ready"] = True

    instrument_completion_by_phase = {
        Study1Phase.DELEGATION_EXPECTATION.value: "delegation_expectation",
        Study1Phase.COMPREHENSION_MEASUREMENT.value: "comprehension_measurement",
        Study1Phase.POST_SURVEY.value: "post_survey",
    }
    for response in exported.get("instrument_responses") or []:
        completion_prefix = instrument_completion_by_phase.get(
            str(response.get("phase") or "")
        )
        if completion_prefix:
            role = str(response.get("role") or "")
            completion[f"{completion_prefix}:{role}"] = True

    return completion


def project_formal_session(
    session: Mapping[str, Any], data: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    projected = copy.deepcopy(dict(session))
    if projected.get("protocol_mode") == "formal_v2":
        projected["completion"] = project_formal_completion(projected, data)
    return projected


def formal_readiness(session: Mapping[str, Any]) -> dict[str, Any]:
    current = Study1Phase(session.get("phase", Study1Phase.SETUP))
    index = PHASE_ORDER.index(current)
    if index + 1 >= len(PHASE_ORDER):
        return {
            "ready_to_advance": False,
            "next_phase": None,
            "missing_prerequisites": [],
        }

    target = PHASE_ORDER[index + 1]
    completion = session.get("completion") or {}
    missing: list[str] = []

    if target is Study1Phase.MATERIAL_READING and session.get("require_consent"):
        missing.extend(
            f"consent:{role.value}"
            for role in HUMAN_ROLES
            if not completion.get(f"consent:{role.value}")
        )
    elif target is Study1Phase.PRE_VOTE:
        missing.extend(
            f"material_ack:{role.value}"
            for role in HUMAN_ROLES
            if not completion.get(f"material_ack:{role.value}")
        )
    elif target is Study1Phase.PROXY_CONFIGURATION:
        missing.extend(
            f"pre_individual:{role.value}"
            for role in HUMAN_ROLES
            if not completion.get(f"pre_individual:{role.value}")
        )
    elif target is Study1Phase.PROXY_MEETING:
        for key in (
            "proxy_config:principal",
            "proxy_ready:teammate_1",
            "proxy_ready:teammate_2",
        ):
            if not completion.get(key):
                missing.append(key)
    elif target is Study1Phase.TENTATIVE_DECISION:
        if not completion.get("proxy_meeting_ended"):
            missing.append("proxy_meeting_ended")
    elif target is Study1Phase.DELEGATION_EXPECTATION:
        missing.extend(
            f"tentative_individual:{role.value}"
            for role in (Study1Role.TEAMMATE_1, Study1Role.TEAMMATE_2)
            if not completion.get(f"tentative_individual:{role.value}")
        )
    elif target is Study1Phase.REVIEW:
        for key in ("delegation_expectation:principal", "summary_artifact_ready"):
            if not completion.get(key):
                missing.append(key)
    elif target is Study1Phase.COMPREHENSION_MEASUREMENT:
        for key in ("review_opened:principal", "review_reading_recorded:principal"):
            if not completion.get(key):
                missing.append(key)
        if session.get("minimum_review_seconds") not in (None, 0):
            if not completion.get("minimum_review_time_met:principal"):
                missing.append("minimum_review_time_met:principal")
    elif target is Study1Phase.HANDOFF:
        if not completion.get("comprehension_measurement:principal"):
            missing.append("comprehension_measurement:principal")
    elif target is Study1Phase.SYNC_MEETING:
        if not completion.get("handoff_complete"):
            missing.append("handoff_complete")
    elif target is Study1Phase.FINAL_DECISION:
        if not completion.get("sync_meeting_ended"):
            missing.append("sync_meeting_ended")
    elif target is Study1Phase.FOLLOWUP_TASK:
        if not completion.get("team_final_locked"):
            missing.append("team_final_locked")
        missing.extend(
            f"final_individual:{role.value}"
            for role in HUMAN_ROLES
            if not completion.get(f"final_individual:{role.value}")
        )
    elif target is Study1Phase.POST_SURVEY:
        if not completion.get("followup_task_locked"):
            missing.append("followup_task_locked")
    elif target is Study1Phase.COMPLETED:
        missing.extend(
            f"post_survey:{role.value}"
            for role in HUMAN_ROLES
            if not completion.get(f"post_survey:{role.value}")
        )

    return {
        "ready_to_advance": not missing,
        "next_phase": target.value,
        "missing_prerequisites": missing,
    }


def formal_capabilities(session: Mapping[str, Any], role: str) -> dict[str, bool]:
    projected = capabilities_for(session, role)
    if session.get("protocol_mode") != "formal_v2":
        return projected

    completion = session.get("completion") or {}
    phase = str(session.get("phase") or "")
    role_name = str(role or "")
    projected.update(
        {
            "submit_pre_individual": (
                phase == Study1Phase.PRE_VOTE.value
                and role_name in {item.value for item in HUMAN_ROLES}
                and not completion.get(f"pre_individual:{role_name}")
            ),
            "submit_tentative_individual": (
                phase == Study1Phase.TENTATIVE_DECISION.value
                and role_name in {
                    Study1Role.TEAMMATE_1.value,
                    Study1Role.TEAMMATE_2.value,
                }
                and not completion.get(f"tentative_individual:{role_name}")
            ),
            "submit_final_individual": (
                phase == Study1Phase.FINAL_DECISION.value
                and role_name in {item.value for item in HUMAN_ROLES}
                and not completion.get(f"final_individual:{role_name}")
            ),
            "edit_team_final": (
                phase == Study1Phase.FINAL_DECISION.value
                and not completion.get("team_final_locked")
            ),
            "confirm_team_final": (
                phase == Study1Phase.FINAL_DECISION.value
                and not completion.get("team_final_locked")
            ),
            "edit_followup_task": (
                phase == Study1Phase.FOLLOWUP_TASK.value
                and not completion.get("followup_task_locked")
            ),
            "confirm_followup_task": (
                phase == Study1Phase.FOLLOWUP_TASK.value
                and not completion.get("followup_task_locked")
            ),
            "submit_post_survey": (
                phase == Study1Phase.POST_SURVEY.value
                and role_name in {item.value for item in HUMAN_ROLES}
                and not completion.get(f"post_survey:{role_name}")
            ),
            "submit_delegation_expectation": (
                phase == Study1Phase.DELEGATION_EXPECTATION.value
                and role_name == Study1Role.PRINCIPAL.value
                and not completion.get(f"delegation_expectation:{role_name}")
            ),
            "submit_comprehension_measurement": (
                phase == Study1Phase.COMPREHENSION_MEASUREMENT.value
                and role_name == Study1Role.PRINCIPAL.value
                and not completion.get(f"comprehension_measurement:{role_name}")
            ),
        }
    )
    return projected
