from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

from .base import CompletionResult, Provider, ProviderError, StreamEvent, ToolSpec, Usage


class OpenAIProvider(Provider):
    """
    Talks to OpenAI's Chat Completions API. Because that API's message
    format differs a fair bit from Anthropic's (tool calls live on the
    assistant message as `tool_calls`, and results come back as separate
    `role: tool` messages keyed by `tool_call_id`), most of this file is
    translation to/from the normalized block format used elsewhere.
    """

    name = "openai"

    def __init__(
        self,
        model: str,
        api_key: str,
        max_tokens: int = 4096,
        base_url: str = None,
        extra_headers: Dict[str, str] = None,
        **kw: Any,
    ) -> None:
        super().__init__(model, **kw)
        try:
            import openai
        except ImportError as e:
            raise ProviderError(
                "The 'openai' package is required. Install with: pip install openai"
            ) from e
        if not api_key:
            raise ProviderError(
                "Missing API key for this provider. Set the environment variable "
                "named in provider_options in your config."
            )
        client_kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        if extra_headers:
            client_kwargs["default_headers"] = extra_headers
        self._client = openai.OpenAI(**client_kwargs)
        self.max_tokens = max_tokens

    def _to_openai_messages(self, messages: List[Dict[str, Any]], system: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            role = m["role"]
            text_parts = [b["text"] for b in m["content"] if b["type"] == "text"]
            tool_uses = [b for b in m["content"] if b["type"] == "tool_use"]
            tool_results = [b for b in m["content"] if b["type"] == "tool_result"]

            if role == "assistant" and tool_uses:
                msg: Dict[str, Any] = {"role": "assistant", "content": " ".join(text_parts) or None}
                msg["tool_calls"] = [
                    {
                        "id": tu["id"],
                        "type": "function",
                        "function": {"name": tu["name"], "arguments": json.dumps(tu["input"])},
                    }
                    for tu in tool_uses
                ]
                out.append(msg)
            elif tool_results:
                for tr in tool_results:
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": tr["tool_use_id"],
                            "content": tr["content"],
                        }
                    )
            else:
                out.append({"role": role, "content": " ".join(text_parts)})
        return out

    def _to_openai_tools(self, tools: List[ToolSpec]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]

    def _from_openai_message(self, message: Any) -> List[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = []
        if message.content:
            blocks.append({"type": "text", "text": message.content})
        for tc in getattr(message, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            blocks.append({"type": "tool_use", "id": tc.id, "name": tc.function.name, "input": args})
        return blocks

    def complete(self, messages, system, tools) -> CompletionResult:
        kwargs: Dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=self._to_openai_messages(messages, system),
        )
        if tools:
            kwargs["tools"] = self._to_openai_tools(tools)
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"OpenAI API error: {e}") from e
        choice = resp.choices[0]
        stop_reason = "tool_use" if choice.finish_reason == "tool_calls" else "end_turn"
        usage = resp.usage
        return CompletionResult(
            content=self._from_openai_message(choice.message),
            stop_reason=stop_reason,
            usage=Usage(usage.prompt_tokens, usage.completion_tokens) if usage else Usage(),
        )

    def stream(self, messages, system, tools, on_event: Callable[[StreamEvent], None]) -> CompletionResult:
        kwargs: Dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=self._to_openai_messages(messages, system),
            stream=True,
        )
        if tools:
            kwargs["tools"] = self._to_openai_tools(tools)

        text_acc = ""
        tool_calls: Dict[int, Dict[str, Any]] = {}
        finish_reason = "stop"
        try:
            for chunk in self._client.chat.completions.create(**kwargs):
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta
                if delta.content:
                    text_acc += delta.content
                    on_event(StreamEvent(type="text_delta", text=delta.content))
                for tc in delta.tool_calls or []:
                    slot = tool_calls.setdefault(
                        tc.index, {"id": "", "name": "", "arguments": ""}
                    )
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                        on_event(StreamEvent(type="tool_use_start", tool_id=slot["id"], tool_name=slot["name"]))
                    if tc.function and tc.function.arguments:
                        slot["arguments"] += tc.function.arguments
                        on_event(StreamEvent(type="tool_use_delta", tool_input_delta=tc.function.arguments))
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"OpenAI API error: {e}") from e

        on_event(StreamEvent(type="message_stop"))

        content: List[Dict[str, Any]] = []
        if text_acc:
            content.append({"type": "text", "text": text_acc})
        for slot in tool_calls.values():
            try:
                args = json.loads(slot["arguments"]) if slot["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            content.append({"type": "tool_use", "id": slot["id"], "name": slot["name"], "input": args})

        stop_reason = "tool_use" if finish_reason == "tool_calls" else "end_turn"
        return CompletionResult(content=content, stop_reason=stop_reason, usage=Usage())
