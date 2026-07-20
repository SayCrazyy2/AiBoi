"""
MCP (Model Context Protocol) client built on the official MCP Python SDK.

Uses ``mcp.ClientSession`` with the stdio transport to communicate with MCP
server child processes.  The public API is deliberately synchronous so the
rest of the codebase (manager, REPL, bots) can use it without any asyncio
awareness — a background thread owns the event loop and all SDK
coroutines are marshalled through it.

Interface (unchanged from the previous lightweight client):

    client = MCPClient(name, command, args, env)
    client.start(timeout=15)
    client.tools               # list[dict] with name/description/inputSchema
    client.call_tool(name, args) -> str
    client.stop()
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

PROTOCOL_VERSION = "2024-11-05"  # kept for reference; SDK negotiates its own


class MCPError(RuntimeError):
    pass


class MCPClient:
    """Synchronous wrapper around the official async MCP ``ClientSession``."""

    def __init__(
        self,
        name: str,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        self.name = name
        self._command = command
        self._args = args
        self._env = env or None
        self.tools: List[Dict[str, Any]] = []

        # -- internal state -------------------------------------------------
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[ClientSession] = None
        self._stdio_cm: Optional[Any] = None       # async context manager
        self._session_cm: Optional[ClientSession] = None
        self._stderr_file: Optional[Any] = None  # tempfile for stderr capture
        self._ready = threading.Event()
        self._start_error: Optional[Exception] = None
        self._stopped = False

    # -- public lifecycle ---------------------------------------------------

    def start(self, timeout: float = 15.0) -> None:
        """Launch the server subprocess, initialise the session, and list tools."""
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"mcp-{self.name}")
        self._thread.start()

        if not self._ready.wait(timeout=timeout):
            self.stop()
            raise MCPError(f"[{self.name}] timed out after {timeout:.0f}s waiting for initialization")

        if self._start_error:
            self.stop()
            raise self._start_error

    def stop(self) -> None:
        """Cleanly close the session and terminate the server subprocess."""
        if self._stopped:
            return
        self._stopped = True

        loop = self._loop
        if loop and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(self._async_cleanup(), loop)  # type: ignore[arg-type]
            try:
                fut.result(timeout=5)
            except Exception:  # noqa: BLE001
                pass
            loop.call_soon_threadsafe(loop.stop)

        if self._thread:
            self._thread.join(timeout=5)

    # -- public tool call ---------------------------------------------------

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: float = 60.0) -> str:
        """Call a tool on the MCP server and return its text output."""
        loop = self._loop
        if loop is None or not loop.is_running():
            raise MCPError(f"[{self.name}] session is not running")

        fut = asyncio.run_coroutine_threadsafe(
            self._async_call_tool(tool_name, arguments),
            loop,  # type: ignore[arg-type]
        )
        try:
            return fut.result(timeout=timeout)
        except MCPError:
            raise
        except Exception as exc:
            stderr_tail = self._read_stderr_tail(20)
            detail = "\n".join(stderr_tail) if stderr_tail else str(exc)
            raise MCPError(f"[{self.name}] tools/call '{tool_name}' failed: {detail}") from exc

    # -- background thread --------------------------------------------------

    def _run(self) -> None:
        """Entry point for the background thread — owns the event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_init())
        except Exception as exc:  # noqa: BLE001
            self._start_error = MCPError(f"[{self.name}] initialization failed: {exc}")
            self._ready.set()
            return

        # Keep the loop alive so call_tool can submit coroutines later.
        self._loop.run_forever()

        # After loop.stop() — final cleanup.
        try:
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
        except Exception:  # noqa: BLE001
            pass
        self._loop.close()

    async def _async_init(self) -> None:
        """Open the stdio transport + ClientSession, initialise, and list tools."""
        # Merge provided env with the current environment so the child
        # process still has PATH, HOME, etc.
        full_env: Optional[Dict[str, str]] = None
        if self._env:
            full_env = {**os.environ, **self._env}

        # Use a real temp file for stderr — anyio.open_process needs an
        # object with a fileno() method, which io.StringIO doesn't have.
        self._stderr_file = tempfile.TemporaryFile(mode="w+", prefix=f"mcp-{self.name}-", suffix=".log")

        server_params = StdioServerParameters(
            command=self._command,
            args=self._args,
            env=full_env,
        )

        # Enter the async context managers manually so the session stays
        # alive for the lifetime of the client (not just one coroutine).
        self._stdio_cm = stdio_client(server_params, errlog=self._stderr_file)
        read_stream, write_stream = await self._stdio_cm.__aenter__()

        self._session_cm = ClientSession(
            read_stream,
            write_stream,
            client_info=types.Implementation(name="ai-cli-assistant", version="0.1.0"),
        )
        self._session = await self._session_cm.__aenter__()

        await self._session.initialize()

        # List tools and convert to the dict format the manager expects.
        result = await self._session.list_tools()
        self.tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.inputSchema
                if t.inputSchema
                else {"type": "object", "properties": {}},
            }
            for t in result.tools
        ]

        self._ready.set()

    async def _async_call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool and extract text from the response content blocks."""
        assert self._session is not None
        result = await self._session.call_tool(tool_name, arguments)

        text_parts: List[str] = []
        for block in result.content:
            if isinstance(block, types.TextContent):
                text_parts.append(block.text)
            elif isinstance(block, types.ImageContent):
                text_parts.append(json.dumps({"type": "image", "mimeType": block.mimeType, "data": block.data}))
            elif isinstance(block, types.EmbeddedResource):
                res = block.resource
                if isinstance(res, types.TextResourceContents):
                    text_parts.append(res.text)
                else:
                    text_parts.append(json.dumps({"type": "resource", "uri": str(res.uri)}))
            else:
                # Unknown content block — serialise it.
                text_parts.append(json.dumps(block.model_dump(mode="json", exclude_none=True)))

        text = "\n".join(text_parts) if text_parts else ""
        if result.isError:
            raise MCPError(text or f"[{self.name}] tool '{tool_name}' returned an error")
        return text

    async def _async_cleanup(self) -> None:
        """Exit the context managers in reverse order."""
        # Suppress exceptions during teardown — we're shutting down anyway.
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._session_cm = None
            self._session = None

        if self._stdio_cm is not None:
            try:
                await self._stdio_cm.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._stdio_cm = None

        if self._stderr_file is not None:
            try:
                self._stderr_file.close()
            except Exception:  # noqa: BLE001
                pass
            self._stderr_file = None

    # -- misc ----------------------------------------------------------------

    def _read_stderr_tail(self, n: int = 200) -> List[str]:
        """Read the last *n* lines of captured server stderr."""
        if self._stderr_file is None:
            return []
        try:
            self._stderr_file.seek(0)
            lines = self._stderr_file.read().splitlines()
            return lines[-n:] if lines else []
        except Exception:  # noqa: BLE001
            return []

    @property
    def stderr_lines(self) -> List[str]:
        """Return the last 200 lines of server stderr output (for debugging)."""
        return self._read_stderr_tail(200)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MCPClient '{self.name}' tools={len(self.tools)} running={self._loop is not None and self._loop.is_running()}>"

    def __enter__(self) -> "MCPClient":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()
