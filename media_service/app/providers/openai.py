from __future__ import annotations

from collections.abc import AsyncIterator
import io
import wave

from openai import AsyncOpenAI

from .base import AsrResult


def _wav_file(pcm_s16le: bytes, sample_rate: int = 48000) -> io.BytesIO:
    output = io.BytesIO()
    with wave.open(output, "wb") as value:
        value.setnchannels(1)
        value.setsampwidth(2)
        value.setframerate(sample_rate)
        value.writeframes(pcm_s16le)
    output.seek(0)
    output.name = "utterance.wav"
    return output


class OpenAIAsrProvider:
    def __init__(self, model: str, api_key: str, *, client=None):
        self.model = model
        self.version = f"openai:{model}"
        self.client = client or AsyncOpenAI(api_key=api_key)

    async def transcribe(self, audio: AsyncIterator[bytes], *, speaker: str):
        pcm = b""
        async for chunk in audio:
            pcm += chunk
        response = await self.client.audio.transcriptions.create(
            model=self.model,
            file=_wav_file(pcm),
            response_format="verbose_json",
        )
        segments = getattr(response, "segments", None) or []
        if segments:
            for segment in segments:
                start = getattr(segment, "start", 0)
                end = getattr(segment, "end", start)
                yield AsrResult(
                    text=getattr(segment, "text", "").strip(),
                    start_ms=round(start * 1000),
                    end_ms=max(round(end * 1000), round(start * 1000) + 1),
                    confidence=None,
                    is_final=True,
                )
            return
        text = getattr(response, "text", "").strip()
        if text:
            duration_ms = max(1, len(pcm) // 96)
            yield AsrResult(text, 0, duration_ms, None, True)


class OpenAILanguageModelProvider:
    def __init__(self, model: str, api_key: str):
        self.model = model
        self.version = f"openai:{model}"
        self.client = AsyncOpenAI(api_key=api_key)

    async def complete(self, *, system_prompt: str, input_text: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_text},
            ],
        )
        return response.choices[0].message.content or ""


class OpenAITtsProvider:
    def __init__(self, model: str, voice: str, api_key: str):
        self.model = model
        self.voice = voice
        self.version = f"openai:{model}:{voice}"
        self.client = AsyncOpenAI(api_key=api_key)

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        async with self.client.audio.speech.with_streaming_response.create(
            model=self.model, voice=self.voice, input=text, response_format="pcm"
        ) as response:
            async for chunk in response.iter_bytes():
                yield chunk
