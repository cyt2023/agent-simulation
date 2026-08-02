from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PcmFrame:
    data: bytes
    sample_rate_hz: int
    channels: int
    sequence_no: int

    def __post_init__(self) -> None:
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if self.channels <= 0:
            raise ValueError("channels must be positive")
        if self.sequence_no < 0:
            raise ValueError("sequence_no must be non-negative")
