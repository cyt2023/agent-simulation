from __future__ import annotations

from array import array
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Utterance:
    pcm_s16le: bytes
    start_ms: int
    end_ms: int


class VoiceActivityBuffer:
    def __init__(
        self,
        *,
        sample_rate: int = 48000,
        threshold: int = 350,
        min_speech_ms: int = 250,
        end_silence_ms: int = 600,
    ):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.min_speech_ms = min_speech_ms
        self.end_silence_ms = end_silence_ms
        self.elapsed_ms = 0
        self.start_ms: int | None = None
        self.speech_ms = 0
        self.silence_ms = 0
        self.chunks: list[bytes] = []

    def _duration_ms(self, pcm_s16le: bytes) -> int:
        return round((len(pcm_s16le) // 2) * 1000 / self.sample_rate)

    @staticmethod
    def _rms(pcm_s16le: bytes) -> float:
        samples = array("h")
        samples.frombytes(pcm_s16le)
        if not samples:
            return 0
        return math.sqrt(sum(sample * sample for sample in samples) / len(samples))

    def feed(self, pcm_s16le: bytes) -> list[Utterance]:
        duration_ms = self._duration_ms(pcm_s16le)
        active = self._rms(pcm_s16le) >= self.threshold
        if self.start_ms is None and active:
            self.start_ms = self.elapsed_ms
        if self.start_ms is not None:
            self.chunks.append(pcm_s16le)
            if active:
                self.speech_ms += duration_ms
                self.silence_ms = 0
            else:
                self.silence_ms += duration_ms
        self.elapsed_ms += duration_ms
        if self.start_ms is None or self.silence_ms < self.end_silence_ms:
            return []
        utterance = None
        if self.speech_ms >= self.min_speech_ms:
            utterance = Utterance(
                pcm_s16le=b"".join(self.chunks),
                start_ms=self.start_ms,
                end_ms=self.elapsed_ms,
            )
        self.start_ms = None
        self.speech_ms = 0
        self.silence_ms = 0
        self.chunks = []
        return [utterance] if utterance else []

    def flush(self) -> list[Utterance]:
        if self.start_ms is None:
            return []
        utterance = None
        if self.speech_ms >= self.min_speech_ms:
            utterance = Utterance(
                pcm_s16le=b"".join(self.chunks),
                start_ms=self.start_ms,
                end_ms=self.elapsed_ms,
            )
        self.start_ms = None
        self.speech_ms = 0
        self.silence_ms = 0
        self.chunks = []
        return [utterance] if utterance else []
