"""Domain constants shared by the Study 1 service.

Database rows are added in the authentication/data commits.  Keeping the role
and phase vocabulary here gives the state machine, permissions, routes, export,
and frontend contract one canonical spelling.
"""

from __future__ import annotations

from enum import StrEnum


class Study1Role(StrEnum):
    PRINCIPAL = "principal"
    TEAMMATE_1 = "teammate_1"
    TEAMMATE_2 = "teammate_2"
    RESEARCHER = "researcher"
    PROXY = "proxy"


HUMAN_ROLES = (
    Study1Role.PRINCIPAL,
    Study1Role.TEAMMATE_1,
    Study1Role.TEAMMATE_2,
)


class Study1Phase(StrEnum):
    SETUP = "SETUP"
    MATERIAL_READING = "MATERIAL_READING"
    PRE_VOTE = "PRE_VOTE"
    PROXY_CONFIGURATION = "PROXY_CONFIGURATION"
    PROXY_MEETING = "PROXY_MEETING"
    TENTATIVE_DECISION = "TENTATIVE_DECISION"
    DELEGATION_EXPECTATION = "DELEGATION_EXPECTATION"
    REVIEW = "REVIEW"
    COMPREHENSION_MEASUREMENT = "COMPREHENSION_MEASUREMENT"
    HANDOFF = "HANDOFF"
    SYNC_MEETING = "SYNC_MEETING"
    FINAL_DECISION = "FINAL_DECISION"
    FOLLOWUP_TASK = "FOLLOWUP_TASK"
    POST_SURVEY = "POST_SURVEY"
    COMPLETED = "COMPLETED"


PHASE_ORDER = tuple(Study1Phase)
PHASE_SCHEMA_VERSION = "1.0"
