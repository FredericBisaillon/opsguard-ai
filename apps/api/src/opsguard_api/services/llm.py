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


@dataclass(frozen=True)
class LLMReviewTaskToolCallData:
    tool_name: str
    arguments: dict[str, Any]


class LLMClient(Protocol):
    model: str

    def validate_configuration(self) -> None:
        pass

    def generate_answer(self, messages: Sequence[LLMMessage]) -> LLMAnswerData:
        pass

    def suggest_review_task(
        self,
        messages: Sequence[LLMMessage],
    ) -> LLMReviewTaskToolCallData | None:
        pass


CREATE_REVIEW_TASK_TOOL_NAME = "create_review_task"

CREATE_REVIEW_TASK_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": CREATE_REVIEW_TASK_TOOL_NAME,
        "description": (
            "Propose one review task grounded in the retrieved document sources. "
            "Call this tool only when a concrete issue is supported by a provided "
            "chunk."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "document_id": {
                    "type": "integer",
                    "description": "The document_id from a provided source.",
                },
                "chunk_id": {
                    "type": ["integer", "null"],
                    "description": (
                        "The chunk_id from the provided source that supports the "
                        "task. Use null only if no specific chunk can support the "
                        "issue."
                    ),
                },
                "title": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 255,
                },
                "description": {
                    "type": ["string", "null"],
                    "maxLength": 4000,
                },
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "evidence": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 1200,
                    "description": "A short quote or paraphrased evidence snippet.",
                },
                "reason": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 1000,
                    "description": "A short explanation for why this task is needed.",
                },
            },
            "required": [
                "document_id",
                "chunk_id",
                "title",
                "description",
                "severity",
                "evidence",
                "reason",
            ],
        },
    },
}


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

    def suggest_review_task(
        self,
        messages: Sequence[LLMMessage],
    ) -> LLMReviewTaskToolCallData | None:
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
                tools=cast(Any, [CREATE_REVIEW_TASK_TOOL]),
                tool_choice="auto",
                temperature=0.0,
            )
        except OpenAIError as exc:
            raise LLMProviderError("LLM provider failed.") from exc

        try:
            tool_calls = response.choices[0].message.tool_calls
        except (AttributeError, IndexError) as exc:
            raise LLMResponseError(
                "LLM provider returned an unexpected response."
            ) from exc

        return _parse_review_task_tool_call(tool_calls)


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


def _parse_review_task_tool_call(
    tool_calls: Any,
) -> LLMReviewTaskToolCallData | None:
    if not tool_calls:
        return None

    if len(tool_calls) != 1:
        raise LLMResponseError("LLM provider returned multiple tool calls.")

    tool_call = tool_calls[0]
    try:
        function_name = tool_call.function.name
        function_arguments = tool_call.function.arguments
    except AttributeError as exc:
        raise LLMResponseError(
            "LLM provider returned an unexpected tool call."
        ) from exc

    if function_name != CREATE_REVIEW_TASK_TOOL_NAME:
        raise LLMResponseError("LLM provider returned an unsupported tool call.")

    if not isinstance(function_arguments, str) or not function_arguments.strip():
        raise LLMResponseError("LLM provider returned empty tool arguments.")

    try:
        payload: Any = json.loads(function_arguments)
    except json.JSONDecodeError as exc:
        raise LLMResponseError("LLM provider returned invalid tool JSON.") from exc

    if not isinstance(payload, dict):
        raise LLMResponseError("LLM provider returned invalid tool arguments.")

    return LLMReviewTaskToolCallData(
        tool_name=function_name,
        arguments=payload,
    )
