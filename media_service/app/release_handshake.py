from __future__ import annotations

from typing import Any, Mapping


class ReleaseHandshakeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_release_handshake(
    payload: Mapping[str, Any],
    *,
    expected_release_id: str | None,
    expected_checksum: str | None,
) -> None:
    if not expected_release_id and not expected_checksum:
        return
    release = payload.get("release")
    if not isinstance(release, Mapping):
        raise ReleaseHandshakeError(
            "RELEASE_IDENTITY_REQUIRED",
            "A media command must include the frozen Study 1 release identity",
        )
    if expected_release_id and release.get("release_id") != expected_release_id:
        raise ReleaseHandshakeError(
            "RELEASE_ID_MISMATCH",
            "A release_id does not match the media service release",
        )
    if expected_checksum and release.get("checksum") != expected_checksum:
        raise ReleaseHandshakeError(
            "RELEASE_CHECKSUM_MISMATCH",
            "A release checksum does not match the media service release",
        )
