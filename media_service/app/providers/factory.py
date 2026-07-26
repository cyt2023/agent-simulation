from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from .azure import AzureAsrProvider, AzureLanguageModelProvider, AzureTtsProvider
from .base import LanguageModelProvider, StreamingAsrProvider, StreamingTtsProvider
from .mock import MockAsrProvider, MockLanguageModelProvider, MockTtsProvider
from .openai import OpenAIAsrProvider, OpenAILanguageModelProvider, OpenAITtsProvider


@dataclass(frozen=True)
class ProviderBundle:
    asr: StreamingAsrProvider
    llm: LanguageModelProvider
    tts: StreamingTtsProvider


def create_providers(settings: Settings) -> ProviderBundle:
    provider = settings.media_provider.strip().lower()
    if provider == "mock":
        return ProviderBundle(
            MockAsrProvider(), MockLanguageModelProvider(), MockTtsProvider()
        )
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for MEDIA_PROVIDER=openai")
        return ProviderBundle(
            OpenAIAsrProvider(settings.openai_asr_model, settings.openai_api_key),
            OpenAILanguageModelProvider(
                settings.openai_llm_model, settings.openai_api_key
            ),
            OpenAITtsProvider(
                settings.openai_tts_model,
                settings.openai_tts_voice,
                settings.openai_api_key,
            ),
        )
    if provider == "azure":
        if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY are required"
            )
        arguments = (
            settings.azure_openai_endpoint,
            settings.azure_openai_api_key,
            settings.azure_openai_api_version,
        )
        return ProviderBundle(
            AzureAsrProvider(settings.azure_whisper_deployment, *arguments),
            AzureLanguageModelProvider(settings.azure_openai_deployment, *arguments),
            AzureTtsProvider(
                settings.azure_tts_deployment,
                settings.openai_tts_voice,
                *arguments,
            ),
        )
    raise ValueError(f"Unsupported MEDIA_PROVIDER: {settings.media_provider}")
