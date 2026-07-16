from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import SESSIONS_DIR
from .providers.base import CompletionResult, Provider, ProviderError, StreamEvent, Usage
from .tools.builtin import ToolExecutionError
from .tools.registry import ToolRegistry

MAX_TOOL_ITERATIONS = 10  # guard against infinite tool-call loops


@dataclass
class SessionStats:
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    turns: int = 0

    def add(self, usage: Usage) -> None:
        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens


@dataclass
class Session:
    provider: Provider
    system_prompt: str
    tools: ToolRegistry
    messages: List[Dict[str, Any]] = field(default_factory=list)
    stats: SessionStats = field(default_factory=SessionStats)
    name: Optional[str] = None

    # -- turn execution ---------------------------------------------------

    def _append_user_text(self, text: str) -> None:
        self.messages.append({"role": "user", "content": [{"type": "text", "text": text}]})

    def run_turn(
        self,
        user_text: str,
        on_text: Callable[[str], None],
        on_tool_call: Callable[[str, dict], None],
        on_tool_result: Callable[[str, str, bool], None],
        stream: bool = True,
    ) -> None:
        """
        Runs one full turn: send the user's message, let the model call
        tools as many times as it needs (up to MAX_TOOL_ITERATIONS), and
        stop once it produces a final text answer.
        """
        self._append_user_text(user_text)
        specs = self.tools.all_specs()

        for _ in range(MAX_TOOL_ITERATIONS):
            result = self._complete(specs, on_text, stream)
            self.stats.add(result.usage)
            self.stats.turns += 1
            self.messages.append({"role": "assistant", "content": result.content})

            tool_uses = [b for b in result.content if b["type"] == "tool_use"]
            if not tool_uses or result.stop_reason != "tool_use":
                return

            tool_results = []
            for tu in tool_uses:
                on_tool_call(tu["name"], tu["input"])
                try:
                    output = self.tools.call(tu["name"], tu["input"])
                    is_error = False
                except ToolExecutionError as e:
                    output = str(e)
                    is_error = True
                except Exception as e:  # noqa: BLE001
                    output = f"Unexpected error: {e}"
                    is_error = True
                on_tool_result(tu["name"], output, is_error)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu["id"], "content": output, "is_error": is_error}
                )
            self.messages.append({"role": "user", "content": tool_results})

        on_text("\n[stopped: reached max tool-call iterations for this turn]\n")

    def _complete(self, specs, on_text, stream: bool) -> CompletionResult:
        if stream:
            def handle(ev: StreamEvent) -> None:
                if ev.type == "text_delta":
                    on_text(ev.text)

            return self.provider.stream(self.messages, self.system_prompt, specs, handle)
        else:
            result = self.provider.complete(self.messages, self.system_prompt, specs)
            for block in result.content:
                if block["type"] == "text":
                    on_text(block["text"])
            return result

    # -- persistence --------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider.name,
            "model": self.provider.model,
            "system_prompt": self.system_prompt,
            "messages": self.messages,
            "saved_at": time.time(),
        }

    def save(self, path: Optional[Path] = None) -> Path:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"{self.name or 'session'}.json"
        out_path = path or (SESSIONS_DIR / fname)
        with open(out_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return out_path

    @staticmethod
    def list_saved() -> List[str]:
        if not SESSIONS_DIR.exists():
            return []
        return sorted(p.stem for p in SESSIONS_DIR.glob("*.json"))

    @staticmethod
    def load_messages(name: str) -> Dict[str, Any]:
        path = SESSIONS_DIR / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"No saved session named '{name}'")
        with open(path, "r") as f:
            return json.load(f)
