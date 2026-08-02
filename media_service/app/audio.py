from __future__ import annotations

from pathlib import Path
import wave


class PcmWaveRecorder:
    """Writes mono PCM frames to an auditable per-track WAV file."""

    def __init__(self, path: str | Path, *, sample_rate: int = 48000):
        self.path = Path(path)
        self.sample_rate = sample_rate
        self.bytes_written = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._wave = wave.open(str(self.path), "wb")
        self._wave.setnchannels(1)
        self._wave.setsampwidth(2)
        self._wave.setframerate(sample_rate)
        self.closed = False

    def write(self, pcm_s16le: bytes) -> None:
        if self.closed:
            raise RuntimeError("Recorder is closed")
        self._wave.writeframesraw(pcm_s16le)
        self.bytes_written += len(pcm_s16le)

    def close(self) -> None:
        if not self.closed:
            self._wave.close()
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
