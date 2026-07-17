from __future__ import annotations

from typing import Any, Callable, Dict, List

from .base import CompletionResult, Provider, ProviderError, StreamEvent, ToolSpec, Usage


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str, api_key: str, max_tokens: int = 4096, **kw: Any) -> None:
        super().__init__(model, **kw)
        try:
            import anthropic
        except ImportError as e:
            raise ProviderError(
                "The 'anthropic' package is required. Install with: pip install anthropic"
            ) from e
        if not api_key:
            raise ProviderError(
                "Missing Anthropic API key. Set ANTHROPIC_API_KEY in your environment."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self.max_tokens = max_tokens

    def _to_anthropic_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for m in messages:
            content = []
            for block in m["content"]:
                if block["type"] == "text":
                    content.append({"type": "text", "text": block["text"]})
                elif block["type"] == "tool_use":
                    content.append(
                        {
                            "type": "tool_use",
                            "id": block["id"],
                            "name": block["name"],
                            "input": block["input"],
                        }
                    )
                elif block["type"] == "tool_result":
                    content.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block["tool_use_id"],
                            "content": block["content"],
                            "is_error": block.get("is_error", False),
                        }
                    )
            out.append({"role": m["role"], "content": content})
        return out

    def _to_anthropic_tools(self, tools: List[ToolSpec]) -> List[Dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]

    def _from_anthropic_content(self, content: List[Any]) -> List[Dict[str, Any]]:
        blocks = []
        for block in content:
            if block.type == "text":
                blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                blocks.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                )
        return blocks

    def complete(self, messages, system, tools) -> CompletionResult:
        kwargs: Dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=self._to_anthropic_messages(messages),
        )
        if tools:
            kwargs["tools"] = self._to_anthropic_tools(tools)
        try:
            resp = self._client.messages.create(**kwargs)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Anthropic API error: {e}") from e
        return CompletionResult(
            content=self._from_anthropic_content(resp.content),
            stop_reason=resp.stop_reason or "end_turn",
            usage=Usage(resp.usage.input_tokens, resp.usage.output_tokens),
        )

    def stream(self, messages, system, tools, on_event: Callable[[StreamEvent], None]) -> CompletionResult:
        kwargs: Dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=self._to_anthropic_messages(messages),
        )
        if tools:
            kwargs["tools"] = self._to_anthropic_tools(tools)

        try:
            with self._client.messages.stream(**kwargs) as stream:
                for event in stream:
                    et = event.type
                    if et == "content_block_start" and event.content_block.type == "tool_use":
                        on_event(
                            StreamEvent(
                                type="tool_use_start",
                                tool_id=event.content_block.id,
                                tool_name=event.content_block.name,
                            )
                        )
                    elif et == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            on_event(StreamEvent(type="text_delta", text=delta.text))
                        elif delta.type == "input_json_delta":
                            on_event(StreamEvent(type="tool_use_delta", tool_input_delta=delta.partial_json))
                    elif et == "message_stop":
                        on_event(StreamEvent(type="message_stop"))
                final = stream.get_final_message()
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Anthropic API error: {e}") from e

        return CompletionResult(
            content=self._from_anthropic_content(final.content),
            stop_reason=final.stop_reason or "end_turn",
            usage=Usage(final.usage.input_tokens, final.usage.output_tokens),
        )
