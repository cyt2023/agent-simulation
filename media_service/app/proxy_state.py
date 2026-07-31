from __future__ import annotations

from enum import StrEnum


class ProxyState(StrEnum):
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    TECHNICAL_ISSUE = "technical_issue"
