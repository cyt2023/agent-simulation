from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from livekit import api

from .config import Settings
from .schemas import MediaAccessResponse


class AccessDenied(ValueError):
    pass


_ROOM_ACCESS = {
    "PROXY_MEETING": {"teammate_1", "teammate_2", "proxy"},
    "SYNC_MEETING": {"principal", "teammate_1", "teammate_2"},
}


def _room_session_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "-", value)[:96]


class MediaAccessService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def issue_access(
        self,
        session_id: str,
        phase: str,
        phase_version: int,
        role: str,
        participant_id: str,
    ) -> MediaAccessResponse:
        if role not in _ROOM_ACCESS.get(phase, set()):
            raise AccessDenied(f"Role {role} cannot enter media for {phase}")
        if role == "proxy" and phase != "PROXY_MEETING":
            raise AccessDenied("Proxy cannot enter the synchronous room")
        room_kind = "proxy" if phase == "PROXY_MEETING" else "sync"
        room_name = f"study1-{_room_session_part(session_id)}-{room_kind}-v{phase_version}"
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.settings.livekit_token_ttl_seconds
        )
        return self._issue_token(
            room_name,
            role=role,
            participant_id=participant_id,
            expires_at=expires_at,
            can_publish=True,
        )

    def issue_recorder_access(
        self, session_id: str, phase_version: int
    ) -> MediaAccessResponse:
        room_name = (
            f"study1-{_room_session_part(session_id)}-sync-v{phase_version}"
        )
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.settings.livekit_token_ttl_seconds
        )
        return self._issue_token(
            room_name,
            role="recorder",
            participant_id=f"recorder-{_room_session_part(session_id)}",
            expires_at=expires_at,
            can_publish=False,
        )

    def _issue_token(
        self,
        room_name: str,
        *,
        role: str,
        participant_id: str,
        expires_at: datetime,
        can_publish: bool,
    ) -> MediaAccessResponse:
        grants = api.VideoGrants(
            room_join=True,
            room=room_name,
            can_subscribe=True,
            can_publish=can_publish,
            can_publish_data=False,
            can_publish_sources=["MICROPHONE"] if can_publish else [],
        )
        token = (
            api.AccessToken(
                self.settings.livekit_api_key,
                self.settings.livekit_api_secret,
            )
            .with_identity(participant_id)
            .with_name(role)
            .with_ttl(timedelta(seconds=self.settings.livekit_token_ttl_seconds))
            .with_grants(grants)
            .to_jwt()
        )
        return MediaAccessResponse(
            room_name=room_name,
            url=self.settings.livekit_public_url or self.settings.livekit_url,
            token=token,
            expires_at=expires_at,
            captions_enabled=self.settings.captions_enabled,
        )
