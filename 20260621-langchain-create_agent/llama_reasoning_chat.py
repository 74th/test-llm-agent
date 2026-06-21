"""
A small LangChain ChatModel for llama.cpp llama-server that preserves reasoning.

What it does:
- Calls llama-server's OpenAI-compatible /v1/chat/completions endpoint via the OpenAI SDK.
- Reads non-standard `reasoning_content` when llama-server returns it.
- Stores reasoning in AIMessage.additional_kwargs["reasoning_content"].
- Stores only the final answer in AIMessage.content, so LangGraph checkpoint history is not polluted.

Important:
- llama-server-specific parameters such as `reasoning_format` must be passed via
  OpenAI SDK's `extra_body`, not as top-level kwargs.
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterator, Optional, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai import OpenAI
from pydantic import Field, PrivateAttr


def _lc_message_to_openai(message: BaseMessage) -> dict[str, Any]:
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}

    if isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content}

    if isinstance(message, AIMessage):
        out: dict[str, Any] = {"role": "assistant", "content": message.content}

        if message.tool_calls:
            reasoning_content = message.additional_kwargs.get("reasoning_content")
            if reasoning_content:
                out["reasoning_content"] = reasoning_content

            out["tool_calls"] = []
            for tc in message.tool_calls:
                args = tc.get("args", {})
                if not isinstance(args, str):
                    args = json.dumps(args, ensure_ascii=False)

                out["tool_calls"].append(
                    {
                        "id": tc.get("id") or f"call_{tc['name']}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": args,
                        },
                    }
                )

        return out

    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }

    role = getattr(message, "role", message.type)
    return {"role": role, "content": message.content}


def _extract_response_message_fields(message_obj: Any) -> dict[str, Any]:
    """Extract standard and non-standard fields from an OpenAI SDK message object."""
    if hasattr(message_obj, "model_dump"):
        data = message_obj.model_dump()
        extra = getattr(message_obj, "model_extra", None) or {}
        return {**data, **extra}

    if isinstance(message_obj, dict):
        return dict(message_obj)

    return {}


def _extract_tool_call_chunks(tool_calls_raw: Any) -> list[dict[str, Any]]:
    if not tool_calls_raw:
        return []

    tool_call_chunks: list[dict[str, Any]] = []
    for raw_tool_call in tool_calls_raw:
        tool_call_fields = _extract_response_message_fields(raw_tool_call)
        function_fields = _extract_response_message_fields(
            tool_call_fields.get("function")
        )
        tool_call_chunks.append(
            tool_call_chunk(
                name=function_fields.get("name"),
                args=function_fields.get("arguments"),
                id=tool_call_fields.get("id"),
                index=tool_call_fields.get("index"),
            )
        )

    return tool_call_chunks


class LlamaServerReasoningChatModel(BaseChatModel):
    """Minimal ChatModel for llama.cpp llama-server with reasoning preservation."""

    base_url: str
    api_key: str = "dummy"
    model: str = "local-model"

    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

    # llama-server-specific parameters go here:
    #   {"reasoning_format": "none"}
    #   {"chat_template_kwargs": {"enable_thinking": False}}
    extra_body: dict[str, Any] = Field(default_factory=dict)

    # Retry when llama-server returns no final assistant output. Tool calls are
    # considered valid output even when assistant content is empty.
    max_empty_output_retries: int = 2
    empty_output_retry_sleep: float = 0.5

    _client: OpenAI = PrivateAttr()

    def __init__(self, **data: Any):
        super().__init__(**data)
        self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    @property
    def _llm_type(self) -> str:
        return "llama_server_reasoning_chat"

    def _log_input_messages(self, messages: list[BaseMessage]) -> None:
        print("==== LLM INPUT MESSAGES ====")
        print("count:", len(messages))
        for i, message in enumerate(messages):
            print(
                i,
                type(message).__name__,
                getattr(message, "type", None),
                repr(str(message.content)[:120]),
            )
        print("============================")

    def _build_request(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        openai_messages = [_lc_message_to_openai(message) for message in messages]
        request: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
        }

        if self.temperature is not None:
            request["temperature"] = self.temperature

        if self.max_tokens is not None:
            request["max_tokens"] = self.max_tokens

        if stop:
            request["stop"] = stop

        request.update(kwargs)

        # OpenAI SDK accepts llama-server extensions only via extra_body.
        if self.extra_body:
            request["extra_body"] = self.extra_body

        return request

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | BaseTool | Any],
        *,
        tool_choice: Optional[str | dict[str, Any]] = None,
        **kwargs: Any,
    ):
        openai_tools = [convert_to_openai_tool(tool) for tool in tools]
        bind_kwargs: dict[str, Any] = {"tools": openai_tools, **kwargs}
        if tool_choice is not None:
            bind_kwargs["tool_choice"] = tool_choice
        return self.bind(**bind_kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._log_input_messages(messages)
        request = self._build_request(messages, stop=stop, **kwargs)

        max_attempts = max(1, self.max_empty_output_retries + 1)
        response: Any = None
        choice: Any = None
        msg_fields: dict[str, Any] = {}
        raw_content = ""
        reasoning_content = ""
        content_for_langchain = ""
        tool_calls_raw: Any = None
        retry_count = 0

        for attempt in range(max_attempts):
            retry_count = attempt
            response = self._client.chat.completions.create(**request)

            if not response.choices:
                if attempt < max_attempts - 1:
                    time.sleep(self.empty_output_retry_sleep)
                    continue
                raise ValueError("llama-server returned no chat completion choices")

            choice = response.choices[0]
            response_message = choice.message
            msg_fields = _extract_response_message_fields(response_message)

            raw_content = msg_fields.get("content") or ""
            reasoning_content = (
                msg_fields.get("reasoning_content")
                or msg_fields.get("reasoning")
                or ""
            )

            content_for_langchain = raw_content

            tool_calls_raw = msg_fields.get("tool_calls")
            if content_for_langchain.strip() or tool_calls_raw:
                break

            if attempt < max_attempts - 1:
                time.sleep(self.empty_output_retry_sleep)

        if not content_for_langchain.strip() and not tool_calls_raw:
            raise ValueError(
                "llama-server returned empty assistant content after "
                f"{max_attempts} attempts"
            )

        additional_kwargs: dict[str, Any] = {}
        if reasoning_content:
            additional_kwargs["reasoning_content"] = reasoning_content

        if tool_calls_raw:
            additional_kwargs["tool_calls"] = tool_calls_raw

        response_metadata: dict[str, Any] = {
            "model": getattr(response, "model", None),
            "finish_reason": choice.finish_reason,
            "id": getattr(response, "id", None),
            "empty_output_retry_count": retry_count,
        }

        if hasattr(response, "usage") and response.usage is not None:
            response_metadata["token_usage"] = response.usage.model_dump()

        response_extra = getattr(response, "model_extra", None) or {}
        if "timings" in response_extra:
            response_metadata["timings"] = response_extra["timings"]

        if reasoning_content:
            response_metadata["has_reasoning_content"] = True
            response_metadata["reasoning_content_chars"] = len(reasoning_content)

        ai_message = AIMessage(
            content=content_for_langchain,
            additional_kwargs=additional_kwargs,
            response_metadata=response_metadata,
        )

        llm_output: dict[str, Any] = {
            "model": getattr(response, "model", None),
            "finish_reason": choice.finish_reason,
        }
        if "token_usage" in response_metadata:
            llm_output["token_usage"] = response_metadata["token_usage"]
        if reasoning_content:
            llm_output["reasoning_content"] = reasoning_content

        return ChatResult(
            generations=[ChatGeneration(message=ai_message)],
            llm_output=llm_output,
        )

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        del run_manager

        self._log_input_messages(messages)
        request = self._build_request(messages, stop=stop, **kwargs)
        request["stream"] = True

        response_stream = self._client.chat.completions.create(**request)
        try:
            for response_chunk in response_stream:
                chunk_fields = _extract_response_message_fields(response_chunk)
                choices = chunk_fields.get("choices") or []
                if not choices:
                    continue

                choice_fields = _extract_response_message_fields(choices[0])
                delta_fields = _extract_response_message_fields(
                    choice_fields.get("delta")
                )

                content = delta_fields.get("content") or ""
                reasoning_content = (
                    delta_fields.get("reasoning_content")
                    or delta_fields.get("reasoning")
                    or ""
                )
                tool_call_chunks = _extract_tool_call_chunks(
                    delta_fields.get("tool_calls")
                )

                additional_kwargs: dict[str, Any] = {}
                if reasoning_content:
                    additional_kwargs["reasoning_content"] = reasoning_content

                generation_info: dict[str, Any] = {}
                if model_name := chunk_fields.get("model"):
                    generation_info["model"] = model_name
                if response_id := chunk_fields.get("id"):
                    generation_info["id"] = response_id
                if finish_reason := choice_fields.get("finish_reason"):
                    generation_info["finish_reason"] = finish_reason

                usage_fields = _extract_response_message_fields(
                    chunk_fields.get("usage")
                )
                if usage_fields:
                    generation_info["token_usage"] = usage_fields

                if timings := chunk_fields.get("timings"):
                    generation_info["timings"] = timings

                if not (
                    content or reasoning_content or tool_call_chunks or generation_info
                ):
                    continue

                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content=content,
                        additional_kwargs=additional_kwargs,
                        tool_call_chunks=tool_call_chunks,
                        id=chunk_fields.get("id"),
                    ),
                    generation_info=generation_info or None,
                )
        finally:
            close = getattr(response_stream, "close", None)
            if callable(close):
                close()
