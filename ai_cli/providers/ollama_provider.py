from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

from .base import CompletionResult, Provider, ProviderError, StreamEvent, ToolSpec, Usage


class OllamaProvider(Provider):
    """
    Talks to a local Ollama server (https://ollama.com) via its HTTP API.
    Tool calling requires a model that supports it (e.g. llama3.1+, qwen2.5).
    Older/smaller local models may ignore tools entirely, which is fine --
    they'll just answer from text.
    """

    name = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434", **kw: Any) -> None:
        super().__init__(model, **kw)
        try:
            import requests  # noqa: F401
        except ImportError as e:
            raise ProviderError("The 'requests' package is required for the Ollama provider.") from e
        self.base_url = base_url.rstrip("/")

    def _to_ollama_messages(self, messages: List[Dict[str, Any]], system: str) -> List[Dict[str, Any]]:
        out = [{"role": "system", "content": system}]
        for m in messages:
            text_parts = [b["text"] for b in m["content"] if b["type"] == "text"]
            image_parts = [b for b in m["content"] if b["type"] == "image"]
            tool_uses = [b for b in m["content"] if b["type"] == "tool_use"]
            tool_results = [b for b in m["content"] if b["type"] == "tool_result"]
            if tool_uses:
                out.append(
                    {
                        "role": "assistant",
                        "content": " ".join(text_parts),
                        "tool_calls": [
                            {"function": {"name": tu["name"], "arguments": tu["input"]}} for tu in tool_uses
                        ],
                    }
                )
            elif tool_results:
                for tr in tool_results:
                    out.append({"role": "tool", "content": tr["content"]})
            elif image_parts:
                # Ollama supports images as base64 strings in the "images" field
                msg: Dict[str, Any] = {"role": m["role"], "content": " ".join(text_parts)}
                msg["images"] = [ip["data"] for ip in image_parts]
                out.append(msg)
            else:
                out.append({"role": m["role"], "content": " ".join(text_parts)})
        return out

    def _to_ollama_tools(self, tools: List[ToolSpec]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.input_schema},
            }
            for t in tools
        ]

    def complete(self, messages, system, tools) -> CompletionResult:
        import requests

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._to_ollama_messages(messages, system),
            "stream": False,
        }
        if tools:
            payload["tools"] = self._to_ollama_tools(tools)
        try:
            resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=300)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Ollama error (is `ollama serve` running?): {e}") from e

        msg = data.get("message", {})
        content: List[Dict[str, Any]] = []
        if msg.get("content"):
            content.append({"type": "text", "text": msg["content"]})
        for i, tc in enumerate(msg.get("tool_calls", []) or []):
            fn = tc.get("function", {})
            content.append(
                {"type": "tool_use", "id": f"call_{i}", "name": fn.get("name", ""), "input": fn.get("arguments", {})}
            )
        stop_reason = "tool_use" if msg.get("tool_calls") else "end_turn"
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)
        return CompletionResult(content=content, stop_reason=stop_reason, usage=Usage(prompt_tokens, completion_tokens))

    def stream(self, messages, system, tools, on_event: Callable[[StreamEvent], None]) -> CompletionResult:
        import requests

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self._to_ollama_messages(messages, system),
            "stream": True,
        }
        if tools:
            payload["tools"] = self._to_ollama_tools(tools)

        text_acc = ""
        tool_calls: List[Dict[str, Any]] = []
        usage = Usage()
        try:
            with requests.post(f"{self.base_url}/api/chat", json=payload, stream=True, timeout=300) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    msg = data.get("message", {})
                    if msg.get("content"):
                        text_acc += msg["content"]
                        on_event(StreamEvent(type="text_delta", text=msg["content"]))
                    for tc in msg.get("tool_calls", []) or []:
                        fn = tc.get("function", {})
                        on_event(StreamEvent(type="tool_use_start", tool_name=fn.get("name", "")))
                        tool_calls.append(fn)
                    if data.get("done"):
                        usage = Usage(data.get("prompt_eval_count", 0), data.get("eval_count", 0))
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"Ollama error (is `ollama serve` running?): {e}") from e

        on_event(StreamEvent(type="message_stop"))
        content: List[Dict[str, Any]] = []
        if text_acc:
            content.append({"type": "text", "text": text_acc})
        for i, fn in enumerate(tool_calls):
            content.append({"type": "tool_use", "id": f"call_{i}", "name": fn.get("name", ""), "input": fn.get("arguments", {})})
        stop_reason = "tool_use" if tool_calls else "end_turn"
        return CompletionResult(content=content, stop_reason=stop_reason, usage=usage)
