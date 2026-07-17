"""
A minimal MCP (Model Context Protocol) client over stdio.

MCP servers are child processes that speak newline-delimited JSON-RPC 2.0 on
stdin/stdout. This client is intentionally dependency-free (no official MCP
SDK required) so the CLI works with any MCP server binary. It implements
just enough of the spec to be useful:

    initialize -> tools/list -> tools/call

Notifications and other request types the server sends are read and
ignored unless they're something we care about (kept simple on purpose).
"""

from __future__ import annotations

import json
import subprocess
import threading
from queue import Empty, Queue
from typing import Any, Dict, List, Optional

PROTOCOL_VERSION = "2024-11-05"


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None) -> None:
        self.name = name
        self._command = [command, *args]
        self._env = env or None
        self._proc: Optional[subprocess.Popen] = None
        self._responses: "Queue[dict]" = Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._id_counter = 0
        self._lock = threading.Lock()
        self.tools: List[Dict[str, Any]] = []
        self._stderr_lines: List[str] = []

    # -- process lifecycle -------------------------------------------------

    def start(self, timeout: float = 15.0) -> None:
        import os

        full_env = None
        if self._env:
            full_env = {**os.environ, **self._env}

        try:
            self._proc = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=full_env,
            )
        except FileNotFoundError as e:
            raise MCPError(f"[{self.name}] could not launch '{self._command[0]}': {e}") from e

        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        threading.Thread(target=self._stderr_loop, daemon=True).start()

        self._initialize(timeout=timeout)
        self.tools = self._list_tools(timeout=timeout)

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                self._proc.kill()

    def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._responses.put(msg)

    def _stderr_loop(self) -> None:
        assert self._proc and self._proc.stderr
        for line in self._proc.stderr:
            self._stderr_lines.append(line.rstrip())
            if len(self._stderr_lines) > 200:
                self._stderr_lines.pop(0)

    # -- JSON-RPC plumbing ---------------------------------------------

    def _next_id(self) -> int:
        with self._lock:
            self._id_counter += 1
            return self._id_counter

    def _send(self, payload: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()

    def _request(self, method: str, params: Optional[dict] = None, timeout: float = 30.0) -> Any:
        if self._proc is None or self._proc.poll() is not None:
            stderr = "\n".join(self._stderr_lines[-20:])
            raise MCPError(f"[{self.name}] server process is not running.\n{stderr}")

        req_id = self._next_id()
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})

        import time

        deadline = time.time() + timeout
        pending: List[dict] = []
        while time.time() < deadline:
            try:
                msg = self._responses.get(timeout=0.25)
            except Empty:
                continue
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise MCPError(f"[{self.name}] {method} failed: {msg['error']}")
                return msg.get("result")
            pending.append(msg)  # not ours (e.g. a notification) -- drop it
        raise MCPError(f"[{self.name}] timed out waiting for response to '{method}'")

    def _notify(self, method: str, params: Optional[dict] = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    # -- MCP protocol methods -------------------------------------------

    def _initialize(self, timeout: float) -> None:
        self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "ai-cli-assistant", "version": "0.1.0"},
            },
            timeout=timeout,
        )
        self._notify("notifications/initialized")

    def _list_tools(self, timeout: float) -> List[Dict[str, Any]]:
        result = self._request("tools/list", {}, timeout=timeout)
        return (result or {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: float = 60.0) -> str:
        result = self._request("tools/call", {"name": tool_name, "arguments": arguments}, timeout=timeout)
        content = (result or {}).get("content", [])
        text_parts = []
        for block in content:
            if block.get("type") == "text":
                text_parts.append(block["text"])
            else:
                text_parts.append(json.dumps(block))
        is_error = bool((result or {}).get("isError"))
        text = "\n".join(text_parts) if text_parts else json.dumps(result)
        if is_error:
            raise MCPError(text)
        return text
