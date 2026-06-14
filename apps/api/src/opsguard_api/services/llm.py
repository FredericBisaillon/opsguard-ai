import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast


class LLMClientError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LLMConfigurationError(LLMClientError):
    pass


class LLMProviderError(LLMClientError):
    pass


class LLMResponseError(LLMClientError):
    pass


@dataclass(frozen=True)
class LLMMessage:
    role: Literal["system", "user"]
    content: str


@dataclass(frozen=True)
class LLMAnswerData:
    is_answered: bool
    answer: str
    citations: list[str]


class LLMClient(Protocol):
    model: str

    def validate_configuration(self) -> None:
        pass

    def generate_answer(self, messages: Sequence[LLMMessage]) -> LLMAnswerData:
        pass


class OpenAILLMClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
    ) -> None:
        self._api_key = api_key
        self.model = model

    def validate_configuration(self) -> None:
        if self._api_key is None or not self._api_key.strip():
            raise LLMConfigurationError(
                "OPENAI_API_KEY is required to generate answers."
            )

        if not self.model.strip():
            raise LLMConfigurationError("LLM_MODEL cannot be empty.")

    def generate_answer(self, messages: Sequence[LLMMessage]) -> LLMAnswerData:
        self.validate_configuration()

        try:
            from openai import OpenAI, OpenAIError

            client = OpenAI(api_key=self._api_key)
            api_messages = [
                {"role": message.role, "content": message.content}
                for message in messages
            ]
            response = client.chat.completions.create(
                model=self.model,
                messages=cast(Any, api_messages),
                response_format=cast(Any, {"type": "json_object"}),
                temperature=0.0,
            )
        except OpenAIError as exc:
            raise LLMProviderError("LLM provider failed.") from exc

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError) as exc:
            raise LLMResponseError(
                "LLM provider returned an unexpected response."
            ) from exc

        return _parse_llm_response(content)


def _parse_llm_response(content: str | None) -> LLMAnswerData:
    if content is None or not content.strip():
        raise LLMResponseError("LLM provider returned an empty answer.")

    try:
        payload: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMResponseError("LLM provider returned invalid JSON.") from exc

    if not isinstance(payload, dict):
        raise LLMResponseError("LLM provider returned invalid JSON.")

    is_answered = payload.get("is_answered")
    answer = payload.get("answer")
    citations = payload.get("citations")

    if not isinstance(is_answered, bool):
        raise LLMResponseError("LLM response is missing is_answered.")

    if not isinstance(answer, str):
        raise LLMResponseError("LLM response is missing answer.")

    if not isinstance(citations, list) or not all(
        isinstance(citation, str) for citation in citations
    ):
        raise LLMResponseError("LLM response is missing citations.")

    cleaned_citations = [
        citation.strip() for citation in citations if citation.strip()
    ]
    return LLMAnswerData(
        is_answered=is_answered,
        answer=answer.strip(),
        citations=cleaned_citations,
    )
