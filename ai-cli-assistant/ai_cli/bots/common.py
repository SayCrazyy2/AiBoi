"""
The brains shared by every bot frontend. Telegram and Discord each get a
thin transport layer (polling vs. gateway, their own message-length limits,
their own way of saying "who sent this") that both funnel into BotEngine,
so the command set and the tool-calling loop only exist once.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .. import config as cfgmod
from ..mcp.manager import MCPManager
from ..providers import ProviderError, build_provider
from ..session import Session
from ..tools.registry import ToolRegistry

HELP_TEXT = (
    "Here's what I can do:\n"
    "/help - show this message\n"
    "/reset - clear this chat's conversation history\n"
    "/model [name] - show or switch the model (owner only to change)\n"
    "/system [prompt] - show or set the system prompt for this chat (owner only to change)\n"
    "/tools - list available tools\n"
    "/usage - token usage for this chat\n"
    "/whoami - show your user id and this chat's id\n"
    "\n"
    "Anything else you send is just a normal message to the assistant."
)


class BotEngine:
    def __init__(self, cfg: Dict[str, Any], bot_key: str, connect_mcp: bool = True) -> None:
        self.cfg = cfg
        self.bot_key = bot_key
        self.bot_cfg = cfg["bots"][bot_key]
        self.model_name = self.bot_cfg.get("model") or cfg.get("default_model")
        self.mcp_manager = MCPManager()
        self.tools = ToolRegistry(self.mcp_manager)

        tool_cfg = cfg.get("tools", {})
        self.tools.register_builtin(
            enable_filesystem=tool_cfg.get("enable_filesystem", True),
            # Shell exec and unconfirmed writes are never allowed from a
            # chat bot -- there's no safe place to ask "are you sure?" when
            # the "user" is a Telegram/Discord account that isn't
            # necessarily you.
            enable_shell=False,
            enable_http=tool_cfg.get("enable_http", True),
            confirm_before_write=False,
            confirm_before_shell=False,
            confirm_fn=lambda _msg: False,
        )
        if connect_mcp:
            servers = cfgmod.load_mcp_servers()
            if servers:
                self.mcp_manager.connect_all(servers, quiet=True)

        self._sessions: Dict[str, Session] = {}

    # -- session management -------------------------------------------------

    def _new_session(self) -> Session:
        provider = build_provider(self.model_name, self.cfg)
        return Session(provider=provider, system_prompt=self.cfg.get("default_system_prompt", ""), tools=self.tools)

    def session_for(self, chat_id: str) -> Session:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = self._new_session()
        return self._sessions[chat_id]

    def is_owner(self, user_id: Any) -> bool:
        owner = self.bot_cfg.get("owner_id")
        return owner is None or str(owner) == str(user_id)

    # -- commands -------------------------------------------------------------

    def handle_command(self, chat_id: str, user_id: Any, text: str) -> Optional[str]:
        """Returns a reply if `text` was a recognized command, else None (caller should treat it as a normal message)."""
        stripped = text.strip()
        if not stripped.startswith("/"):
            return None

        parts = stripped[1:].split(maxsplit=1)
        cmd = parts[0].lower().split("@")[0]  # strip telegram's "/model@yourbot" suffix
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("start", "help"):
            return HELP_TEXT
        if cmd == "reset":
            self._sessions.pop(chat_id, None)
            return "Conversation cleared."
        if cmd == "model":
            if not arg:
                return f"Current model: {self.model_name}"
            if not self.is_owner(user_id):
                return "Only the bot owner can switch models."
            if arg not in self.cfg.get("models", {}):
                return f"Unknown model '{arg}'. Known: {', '.join(self.cfg.get('models', {}))}"
            self.model_name = arg
            self._sessions.pop(chat_id, None)
            return f"Switched to {arg}."
        if cmd == "system":
            session = self.session_for(chat_id)
            if not arg:
                return f"Current system prompt:\n{session.system_prompt}"
            if not self.is_owner(user_id):
                return "Only the bot owner can change the system prompt."
            session.system_prompt = arg
            return "System prompt updated for this chat."
        if cmd == "tools":
            names = self.tools.names()
            return "Available tools:\n" + "\n".join(f"- {n}" for n in names) if names else "No tools enabled."
        if cmd == "usage":
            s = self.session_for(chat_id).stats
            return f"turns: {s.turns}\ninput tokens: {s.total_input_tokens}\noutput tokens: {s.total_output_tokens}"
        if cmd in ("whoami", "id"):
            return f"your id: {user_id}\nchat id: {chat_id}"
        return f"Unknown command /{cmd}. Try /help."

    # -- normal messages ----------------------------------------------------

    def reply(self, chat_id: str, text: str) -> str:
        """Runs one full AI turn (tool calls included) and returns the final text, non-streamed."""
        session = self.session_for(chat_id)
        buffer = {"text": ""}

        def on_text(chunk: str) -> None:
            buffer["text"] += chunk

        def on_tool_call(_name: str, _args: dict) -> None:
            pass

        def on_tool_result(_name: str, _output: str, _is_error: bool) -> None:
            pass

        try:
            session.run_turn(text, on_text, on_tool_call, on_tool_result, stream=False)
        except ProviderError as e:
            return f"Error talking to the model: {e}"
        return buffer["text"].strip() or "(no response)"

    def close(self) -> None:
        self.mcp_manager.disconnect_all()
