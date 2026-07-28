from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import uuid


@dataclass(frozen=True)
class TranscriptSegment:
    segment_id: str
    session_id: str
    runtime_id: str
    speaker: str
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None
    is_final: bool
    provider_version: str


class TranscriptBuilder:
    def __init__(self, session_id: str, runtime_id: str, provider_version: str):
        self.session_id = session_id
        self.runtime_id = runtime_id
        self.provider_version = provider_version
        self.segments: list[TranscriptSegment] = []

    def add_final(
        self,
        *,
        speaker: str,
        start_ms: int,
        end_ms: int,
        text: str,
        confidence: float | None,
    ) -> TranscriptSegment:
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError("Transcript timestamps must define a positive range")
        segment = TranscriptSegment(
            segment_id=str(uuid.uuid4()),
            session_id=self.session_id,
            runtime_id=self.runtime_id,
            speaker=speaker,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text.strip(),
            confidence=confidence,
            is_final=True,
            provider_version=self.provider_version,
        )
        self.segments.append(segment)
        return segment

    def checksum(self) -> str:
        canonical = json.dumps(
            [asdict(segment) for segment in self.segments],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
