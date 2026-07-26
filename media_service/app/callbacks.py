from __future__ import annotations

import httpx

from .models import OutboxMessageRow
from .repository import MediaRepository


class CallbackClient:
    def __init__(
        self,
        repository: MediaRepository,
        a_base_url: str,
        internal_key: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.repository = repository
        self.a_base_url = a_base_url.rstrip("/")
        self.internal_key = internal_key
        self.timeout = timeout
        self.transport = transport

    async def deliver(self, message: OutboxMessageRow) -> bool:
        is_artifact = message.message_kind == "artifact"
        envelope = message.payload if is_artifact else {
                "event_id": message.event_id,
                "session_id": message.session_id,
                "phase_version": message.phase_version,
                "event_type": message.event_type,
                "occurred_at": message.occurred_at.isoformat().replace("+00:00", "Z"),
                "payload": message.payload,
            }
        path = (
            f"/api/internal/study1/sessions/{message.session_id}/artifacts"
            if is_artifact
            else "/api/internal/study1/media-events"
        )
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self.transport
            ) as client:
                response = await client.post(
                    f"{self.a_base_url}{path}",
                    headers={"X-Study1-Internal-Key": self.internal_key},
                    json=envelope,
                )
                if response.status_code == 409:
                    self.repository.mark_outbox_discarded(
                        message.event_id,
                        f"Stale callback discarded after HTTP 409: {response.text}",
                    )
                    return False
                response.raise_for_status()
        except (httpx.HTTPError, RuntimeError) as error:
            self.repository.mark_outbox_attempt(message.event_id, str(error))
            return False
        self.repository.mark_outbox_delivered(message.event_id)
        return True

    async def drain(self) -> int:
        delivered = 0
        for message in self.repository.pending_outbox():
            delivered += int(await self.deliver(message))
        return delivered
