from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from .azure import AzureAsrProvider, AzureLanguageModelProvider, AzureTtsProvider
from .base import (
    LanguageModelProvider,
    ProviderCapabilities,
    StreamingAsrProvider,
    StreamingTtsProvider,
)
from .mock import MockAsrProvider, MockLanguageModelProvider, MockTtsProvider
from .openai import OpenAIAsrProvider, OpenAILanguageModelProvider, OpenAITtsProvider
from .openai_realtime import OpenAIRealtimeAsrProvider


class ProviderCapabilityError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderBundle:
    asr: StreamingAsrProvider
    llm: LanguageModelProvider
    tts: StreamingTtsProvider
    capabilities: ProviderCapabilities


def create_providers(settings: Settings) -> ProviderBundle:
    return create_provider_bundle(settings, formal=False)


def create_provider_bundle(settings: Settings, *, formal: bool = False) -> ProviderBundle:
    provider = settings.media_provider.strip().lower()
    if provider == "mock":
        return ProviderBundle(
            MockAsrProvider(),
            MockLanguageModelProvider(),
            MockTtsProvider(),
            ProviderCapabilities(
                streaming_asr=True,
                streaming_llm=True,
                streaming_tts=True,
                batch_asr=False,
            ),
        )
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for MEDIA_PROVIDER=openai")
        if formal and settings.openai_asr_model == "whisper-1":
            raise ProviderCapabilityError(
                "Formal Study 1 requires streaming ASR; whisper-1 is batch ASR"
            )
        asr = (
            OpenAIRealtimeAsrProvider(settings.openai_asr_model, settings.openai_api_key)
            if formal
            else OpenAIAsrProvider(settings.openai_asr_model, settings.openai_api_key)
        )
        return ProviderBundle(
            asr,
            OpenAILanguageModelProvider(
                settings.openai_llm_model, settings.openai_api_key
            ),
            OpenAITtsProvider(
                settings.openai_tts_model,
                settings.openai_tts_voice,
                settings.openai_api_key,
            ),
            ProviderCapabilities(
                streaming_asr=formal,
                streaming_llm=False,
                streaming_tts=True,
                batch_asr=not formal,
            ),
        )
    if provider == "azure":
        if formal:
            raise ProviderCapabilityError(
                "Formal Study 1 requires a streaming ASR adapter; Azure batch ASR is disabled"
            )
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
            ProviderCapabilities(
                streaming_asr=False,
                streaming_llm=False,
                streaming_tts=True,
                batch_asr=True,
            ),
        )
    raise ValueError(f"Unsupported MEDIA_PROVIDER: {settings.media_provider}")
