from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from ..mcp.manager import MCPManager
from ..providers.base import ToolSpec
from .builtin import ToolExecutionError, ToolHandler, make_builtin_tools


class ToolRegistry:
    """
    Single place the tool-calling loop asks: "what tools exist?" and
    "please run this one." Merges local built-in tools with whatever the
    connected MCP servers expose, so the model just sees one flat toolbox.
    """

    def __init__(self, mcp_manager: Optional[MCPManager] = None) -> None:
        self._local: Dict[str, Tuple[ToolSpec, ToolHandler]] = {}
        self._mcp_manager = mcp_manager

    def register_builtin(
        self,
        enable_filesystem: bool,
        enable_shell: bool,
        enable_http: bool,
        confirm_before_write: bool,
        confirm_before_shell: bool,
        confirm_fn: Callable[[str], bool],
        allowed_shell_commands: Optional[List[str]] = None,
    ) -> None:
        for spec, handler in make_builtin_tools(
            enable_filesystem,
            enable_shell,
            enable_http,
            confirm_before_write,
            confirm_before_shell,
            confirm_fn,
            allowed_shell_commands=allowed_shell_commands,
        ):
            self._local[spec.name] = (spec, handler)

    def set_mcp_manager(self, manager: MCPManager) -> None:
        self._mcp_manager = manager

    def all_specs(self) -> List[ToolSpec]:
        specs = [spec for spec, _ in self._local.values()]
        if self._mcp_manager:
            specs.extend(self._mcp_manager.tool_specs())
        return specs

    def names(self) -> List[str]:
        return [s.name for s in self.all_specs()]

    def call(self, name: str, arguments: dict) -> str:
        if name in self._local:
            _, handler = self._local[name]
            return handler(arguments)
        if self._mcp_manager and self._mcp_manager.is_mcp_tool(name):
            return self._mcp_manager.call(name, arguments)
        raise ToolExecutionError(f"Unknown tool: {name}")
