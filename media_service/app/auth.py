from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request


def require_a_service(request: Request, authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {request.app.state.settings.a_to_b_service_token}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid A-to-B service credential")
