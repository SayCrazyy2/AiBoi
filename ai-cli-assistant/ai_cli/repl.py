from __future__ import annotations

from typing import Any, Dict

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm
from rich.rule import Rule

from . import config as cfgmod
from .mcp.manager import MCPManager
from .providers import ProviderError, build_provider
from .session import Session
from .tools.registry import ToolRegistry

HELP_TEXT = """\
[bold]Slash commands[/bold]
  /help                 show this help
  /model [name]         show or switch the active model
  /models               list configured models
  /system <prompt>      change the system prompt for this session
  /tools                list all available tools (built-in + MCP)
  /mcp                  list connected MCP servers
  /save [name]          save the current conversation
  /load <name>          load a previously saved conversation
  /sessions             list saved conversations
  /usage                show token usage for this session
  /clear                clear the current conversation history
  /stream on|off        toggle streaming output
  /exit, /quit          leave
"""


class REPL:
    def __init__(self, cfg: Dict[str, Any], model_name: str, mcp_config_path=None, no_mcp: bool = False) -> None:
        self.console = Console()
        self.cfg = cfg
        self.model_name = model_name
        self.stream = cfg.get("ui", {}).get("stream", True)
        self.mcp_manager = MCPManager()
        self.tools = ToolRegistry(self.mcp_manager)

        tool_cfg = cfg.get("tools", {})
        self.tools.register_builtin(
            enable_filesystem=tool_cfg.get("enable_filesystem", True),
            enable_shell=tool_cfg.get("enable_shell", False),
            enable_http=tool_cfg.get("enable_http", True),
            confirm_before_write=tool_cfg.get("confirm_before_write", True),
            confirm_before_shell=tool_cfg.get("confirm_before_shell", True),
            confirm_fn=self._confirm,
        )

        if not no_mcp:
            servers = cfgmod.load_mcp_servers(mcp_config_path)
            if servers:
                self.console.print("[dim]Connecting to MCP servers...[/dim]")
                self.mcp_manager.connect_all(servers)

        self.session = self._new_session()

    # -- setup ---------------------------------------------------------

    def _confirm(self, prompt: str) -> bool:
        self.console.print(Panel(prompt, title="Confirm", border_style="yellow"))
        return Confirm.ask("Proceed?", default=False)

    def _new_session(self) -> Session:
        provider = build_provider(self.model_name, self.cfg)
        return Session(
            provider=provider,
            system_prompt=self.cfg.get("default_system_prompt", ""),
            tools=self.tools,
        )

    # -- main loop -------------------------------------------------------

    def run(self) -> None:
        self.console.print(
            Panel.fit(
                f"[bold cyan]AI CLI Assistant[/bold cyan]\n"
                f"model: [green]{self.model_name}[/green] ({self.session.provider.name})\n"
                f"tools: {len(self.tools.names())}   mcp servers: {len(self.mcp_manager.list_server_names())}\n"
                f"[dim]Type /help for commands, /exit to quit.[/dim]",
                border_style="cyan",
            )
        )
        try:
            while True:
                try:
                    user_input = self.console.input("[bold blue]you>[/bold blue] ").strip()
                except (EOFError, KeyboardInterrupt):
                    self.console.print()
                    break
                if not user_input:
                    continue
                if user_input.startswith("/"):
                    if self._handle_command(user_input):
                        break
                    continue
                self._handle_message(user_input)
        finally:
            self.mcp_manager.disconnect_all()

    # -- command handling --------------------------------------------------

    def _handle_command(self, raw: str) -> bool:
        """Returns True if the REPL should exit."""
        parts = raw[1:].split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("exit", "quit"):
            return True
        if cmd == "help":
            self.console.print(HELP_TEXT)
        elif cmd == "model":
            if arg:
                self._switch_model(arg)
            else:
                self.console.print(f"current model: [green]{self.model_name}[/green]")
        elif cmd == "models":
            for name, spec in self.cfg.get("models", {}).items():
                marker = "*" if name == self.model_name else " "
                self.console.print(f" {marker} {name}  [dim]({spec['provider']}: {spec['model']})[/dim]")
        elif cmd == "system":
            if arg:
                self.session.system_prompt = arg
                self.console.print("[dim]system prompt updated[/dim]")
            else:
                self.console.print(Panel(self.session.system_prompt, title="system prompt"))
        elif cmd == "tools":
            for spec in self.tools.all_specs():
                self.console.print(f" - [bold]{spec.name}[/bold]: {spec.description}")
        elif cmd == "mcp":
            names = self.mcp_manager.list_server_names()
            self.console.print(", ".join(names) if names else "(no MCP servers connected)")
        elif cmd == "save":
            self.session.name = arg or self.session.name
            path = self.session.save()
            self.console.print(f"[dim]saved to {path}[/dim]")
        elif cmd == "load":
            self._load_session(arg)
        elif cmd == "sessions":
            names = Session.list_saved()
            self.console.print(", ".join(names) if names else "(no saved sessions)")
        elif cmd == "usage":
            s = self.session.stats
            self.console.print(
                f"turns: {s.turns}  input tokens: {s.total_input_tokens}  output tokens: {s.total_output_tokens}"
            )
        elif cmd == "clear":
            self.session.messages.clear()
            self.console.print("[dim]conversation cleared[/dim]")
        elif cmd == "stream":
            if arg in ("on", "off"):
                self.stream = arg == "on"
                self.console.print(f"[dim]streaming {'enabled' if self.stream else 'disabled'}[/dim]")
            else:
                self.console.print("usage: /stream on|off")
        else:
            self.console.print(f"[red]unknown command:[/red] /{cmd}  (try /help)")
        return False

    def _switch_model(self, name: str) -> None:
        if name not in self.cfg.get("models", {}):
            self.console.print(f"[red]unknown model '{name}'.[/red] see /models")
            return
        try:
            old_messages = self.session.messages
            self.model_name = name
            self.session = self._new_session()
            self.session.messages = old_messages
            self.console.print(f"[dim]switched to {name}[/dim]")
        except ProviderError as e:
            self.console.print(f"[red]{e}[/red]")

    def _load_session(self, name: str) -> None:
        if not name:
            self.console.print("usage: /load <name>")
            return
        try:
            data = Session.load_messages(name)
        except FileNotFoundError as e:
            self.console.print(f"[red]{e}[/red]")
            return
        self.session.messages = data["messages"]
        self.session.system_prompt = data.get("system_prompt", self.session.system_prompt)
        self.session.name = name
        self.console.print(f"[dim]loaded '{name}' ({len(self.session.messages)} messages)[/dim]")

    # -- message handling --------------------------------------------------

    def _handle_message(self, text: str) -> None:
        self.console.print(Rule(style="dim"))
        buffer = {"text": ""}

        def on_text(chunk: str) -> None:
            buffer["text"] += chunk
            if self.stream:
                # Live streaming: print raw chunks as they arrive.
                self.console.print(chunk, end="")
            # When not streaming, we hold the text and render it as
            # markdown in one shot once the full response has arrived.

        def on_tool_call(name: str, args: dict) -> None:
            self.console.print(f"\n[yellow]-> calling tool[/yellow] [bold]{name}[/bold]({args})")

        def on_tool_result(name: str, output: str, is_error: bool) -> None:
            color = "red" if is_error else "green"
            preview = output if len(output) < 300 else output[:300] + "..."
            self.console.print(f"[{color}]<- {name} result:[/{color}] {preview}")

        try:
            self.session.run_turn(text, on_text, on_tool_call, on_tool_result, stream=self.stream)
        except ProviderError as e:
            self.console.print(f"\n[red]{e}[/red]")
            return

        self.console.print()
        if not self.stream and self.cfg.get("ui", {}).get("markdown", True) and buffer["text"].strip():
            # Non-streaming mode: nothing has been printed yet, so render
            # the whole answer as markdown at once (headings, code blocks...).
            self.console.print(Markdown(buffer["text"]))
