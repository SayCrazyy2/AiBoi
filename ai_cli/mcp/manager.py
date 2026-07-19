from __future__ import annotations

from typing import Dict, List, Tuple

from ..config import MCPServerConfig
from ..providers.base import ToolSpec
from .client import MCPClient, MCPError

TOOL_PREFIX = "mcp"


def namespaced_tool_name(server_name: str, tool_name: str) -> str:
    return f"{TOOL_PREFIX}__{server_name}__{tool_name}"


class MCPManager:
    """Owns a set of MCP server connections and exposes their tools as one flat list."""

    def __init__(self) -> None:
        self._clients: Dict[str, MCPClient] = {}
        self._errors: List[str] = []

    def connect_all(self, servers: List[MCPServerConfig], quiet: bool = False) -> None:
        for s in servers:
            try:
                client = MCPClient(s.name, s.command, s.args, s.env)
                client.start()
                self._clients[s.name] = client
                if not quiet:
                    print(f"  connected to MCP server '{s.name}' ({len(client.tools)} tools)")
            except MCPError as e:
                self._errors.append(str(e))
                if not quiet:
                    print(f"  ! failed to connect to MCP server '{s.name}': {e}")

    def disconnect_all(self) -> None:
        for client in self._clients.values():
            client.stop()

    def list_server_names(self) -> List[str]:
        return list(self._clients.keys())

    def tool_specs(self) -> List[ToolSpec]:
        specs = []
        for server_name, client in self._clients.items():
            for tool in client.tools:
                specs.append(
                    ToolSpec(
                        name=namespaced_tool_name(server_name, tool["name"]),
                        description=f"[{server_name}] {tool.get('description', '')}".strip(),
                        input_schema=tool.get("inputSchema", {"type": "object", "properties": {}}),
                    )
                )
        return specs

    def is_mcp_tool(self, tool_name: str) -> bool:
        return tool_name.startswith(f"{TOOL_PREFIX}__")

    def _split(self, tool_name: str) -> Tuple[str, str]:
        _, server_name, real_name = tool_name.split("__", 2)
        return server_name, real_name

    def call(self, tool_name: str, arguments: dict) -> str:
        server_name, real_name = self._split(tool_name)
        client = self._clients.get(server_name)
        if client is None:
            raise MCPError(f"No connected MCP server named '{server_name}'")
        return client.call_tool(real_name, arguments)
