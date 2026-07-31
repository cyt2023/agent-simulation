from __future__ import annotations

import pytest


def _command(media_config_checksum: str | None = None):
    from media_service.app.media_config import FrozenMediaConfig

    config = FrozenMediaConfig.default(session_id="session-1", phase_version=5)
    return {
        "session_id": "session-1",
        "phase_version": 5,
        "payload": {
            "media_config": config.to_dict(),
            "media_config_checksum": media_config_checksum or config.checksum,
        },
    }


def test_media_config_checksum_must_match_command():
    from media_service.app.media_config import FrozenMediaConfig, MediaConfigError

    with pytest.raises(MediaConfigError, match="checksum"):
        FrozenMediaConfig.from_command(_command(media_config_checksum="wrong"))


def test_media_config_allows_audio_sources_only():
    from media_service.app.media_config import FrozenMediaConfig, MediaConfigError

    command = _command()
    command["payload"]["media_config"]["publish_sources"] = ["microphone", "camera"]

    with pytest.raises(MediaConfigError, match="audio-only"):
        FrozenMediaConfig.from_command(command)


def test_media_config_round_trips_with_canonical_checksum():
    from media_service.app.media_config import FrozenMediaConfig

    parsed = FrozenMediaConfig.from_command(_command())

    assert parsed.session_id == "session-1"
    assert parsed.phase_version == 5
    assert parsed.streaming.asr is True
    assert parsed.publish_sources == ("microphone",)


def test_media_v2_event_catalog_is_accepted_by_platform_a():
    from media_service.app.media_config import MEDIA_V2_EVENT_TYPES
    from study1.media_gateway import EVENT_TYPES

    assert MEDIA_V2_EVENT_TYPES <= EVENT_TYPES
