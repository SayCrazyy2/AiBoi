"""
Provider abstraction.

Every backend (Anthropic, OpenAI, Ollama, ...) implements `Provider` and
speaks a normalized wire format so the rest of the app (session, tool loop,
REPL) never has to know which API is behind the model.

Normalized message dict shape:
    {"role": "user" | "assistant" | "tool", "content": [Block, ...]}

Block is one of:
    {"type": "text", "text": str}
    {"type": "tool_use", "id": str, "name": str, "input": dict}
    {"type": "tool_result", "tool_use_id": str, "content": str, "is_error": bool}
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON schema for the tool's arguments


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class StreamEvent:
    """One incremental piece of a streamed response."""
    type: str  # "text_delta" | "tool_use_start" | "tool_use_delta" | "message_stop"
    text: str = ""
    tool_id: str = ""
    tool_name: str = ""
    tool_input_delta: str = ""


@dataclass
class CompletionResult:
    content: List[Dict[str, Any]]   # normalized content blocks (see module docstring)
    stop_reason: str                # "end_turn" | "tool_use" | "max_tokens" | ...
    usage: Usage = field(default_factory=Usage)


class Provider(ABC):
    """A chat-completion backend."""

    name: str = "base"

    def __init__(self, model: str, **options: Any) -> None:
        self.model = model
        self.options = options

    @abstractmethod
    def complete(
        self,
        messages: List[Dict[str, Any]],
        system: str,
        tools: List[ToolSpec],
    ) -> CompletionResult:
        """Non-streaming completion. Returns normalized content blocks."""
        raise NotImplementedError

    def stream(
        self,
        messages: List[Dict[str, Any]],
        system: str,
        tools: List[ToolSpec],
        on_event: Callable[[StreamEvent], None],
    ) -> CompletionResult:
        """
        Streaming completion. Default implementation falls back to a single
        non-streaming call and replays it as one text_delta event, so
        providers don't strictly have to implement streaming to be usable.
        """
        result = self.complete(messages, system, tools)
        for block in result.content:
            if block["type"] == "text":
                on_event(StreamEvent(type="text_delta", text=block["text"]))
        on_event(StreamEvent(type="message_stop"))
        return result


class ProviderError(RuntimeError):
    pass
