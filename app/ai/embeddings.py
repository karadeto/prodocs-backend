from openai import AsyncAzureOpenAI, AsyncOpenAI

from app.config import get_settings

_client: AsyncOpenAI | None = None
BATCH_SIZE = 100


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        s = get_settings()
        if s.azure_openai_endpoint:
            _client = AsyncAzureOpenAI(
                azure_endpoint=s.azure_openai_endpoint,
                api_key=s.azure_openai_api_key or "",
                api_version=s.azure_openai_api_version,
            )
        else:
            _client = AsyncOpenAI()
    return _client


async def embed_batch(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = [t[:8000] or " " for t in texts[i : i + BATCH_SIZE]]
        resp = await _get_client().embeddings.create(
            model=s.embedding_model, input=batch, dimensions=s.embedding_dimensions
        )
        out.extend(d.embedding for d in resp.data)
    return out


async def embed_one(text: str) -> list[float]:
    return (await embed_batch([text]))[0]
