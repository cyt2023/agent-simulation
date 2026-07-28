from __future__ import annotations

from openai import AsyncAzureOpenAI

from .openai import OpenAIAsrProvider, OpenAITtsProvider


class AzureLanguageModelProvider:
    def __init__(
        self, deployment: str, endpoint: str, api_key: str, api_version: str
    ):
        self.deployment = deployment
        self.version = f"azure:{deployment}:{api_version}"
        self.client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )

    async def complete(self, *, system_prompt: str, input_text: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.deployment,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_text},
            ],
        )
        return response.choices[0].message.content or ""


class AzureAsrProvider(OpenAIAsrProvider):
    def __init__(self, deployment: str, endpoint: str, api_key: str, api_version: str):
        client = AsyncAzureOpenAI(
            azure_endpoint=endpoint, api_key=api_key, api_version=api_version
        )
        super().__init__(deployment, api_key, client=client)
        self.version = f"azure:{deployment}:{api_version}"


class AzureTtsProvider(OpenAITtsProvider):
    def __init__(
        self,
        deployment: str,
        voice: str,
        endpoint: str,
        api_key: str,
        api_version: str,
    ):
        self.model = deployment
        self.voice = voice
        self.version = f"azure:{deployment}:{voice}:{api_version}"
        self.client = AsyncAzureOpenAI(
            azure_endpoint=endpoint, api_key=api_key, api_version=api_version
        )
