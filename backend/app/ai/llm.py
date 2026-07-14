"""Model factory for pydantic-ai.

Model strings from settings:
  "openai:gpt-4.1-mini"  -> passed straight to pydantic-ai (any provider it supports)
  "azure:<deployment>"   -> Azure OpenAI via explicit client
"""

from typing import Any

from app.config import get_settings


def build_model(name: str) -> Any:
    if not name.startswith("azure:"):
        return name

    from openai import AsyncAzureOpenAI
    from pydantic_ai.providers.openai import OpenAIProvider

    try:  # pydantic-ai renamed OpenAIModel -> OpenAIChatModel in newer versions
        from pydantic_ai.models.openai import OpenAIChatModel as _OpenAIModel
    except ImportError:  # pragma: no cover
        from pydantic_ai.models.openai import OpenAIModel as _OpenAIModel

    s = get_settings()
    client = AsyncAzureOpenAI(
        azure_endpoint=s.azure_openai_endpoint or "",
        api_key=s.azure_openai_api_key or "",
        api_version=s.azure_openai_api_version,
    )
    deployment = name.split(":", 1)[1]
    return _OpenAIModel(deployment, provider=OpenAIProvider(openai_client=client))
