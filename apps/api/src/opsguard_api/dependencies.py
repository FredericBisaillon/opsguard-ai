from fastapi import Depends

from opsguard_api.config import Settings, get_settings
from opsguard_api.services.embeddings import EmbeddingClient, OpenAIEmbeddingClient


def get_embedding_client(
    settings: Settings = Depends(get_settings),
) -> EmbeddingClient:
    return OpenAIEmbeddingClient(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
