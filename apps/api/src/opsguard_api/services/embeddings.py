from collections.abc import Sequence
from typing import Protocol


class EmbeddingClientError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EmbeddingConfigurationError(EmbeddingClientError):
    pass


class EmbeddingProviderError(EmbeddingClientError):
    pass


class EmbeddingClient(Protocol):
    model: str
    dimensions: int

    def validate_configuration(self) -> None:
        pass

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        pass


class OpenAIEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        dimensions: int,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.dimensions = dimensions

    def validate_configuration(self) -> None:
        if self._api_key is None or not self._api_key.strip():
            raise EmbeddingConfigurationError(
                "OPENAI_API_KEY is required to generate embeddings."
            )

        if not self.model.strip():
            raise EmbeddingConfigurationError("EMBEDDING_MODEL cannot be empty.")

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.validate_configuration()
        if not texts:
            return []

        try:
            from openai import OpenAI, OpenAIError

            client = OpenAI(api_key=self._api_key)
            response = client.embeddings.create(
                input=list(texts),
                model=self.model,
                dimensions=self.dimensions,
                encoding_format="float",
            )
        except OpenAIError as exc:
            raise EmbeddingProviderError("Embedding provider failed.") from exc

        embeddings_by_index = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in embeddings_by_index]
