from __future__ import annotations

from typing import Any, Dict

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm
from rich.rule import Rule
from rich.table import Table

from . import config as cfgmod
from .mcp.manager import MCPManager
from .providers import ProviderError, build_provider
from .session import Session
from .tools.registry import ToolRegistry

HELP_TEXT = """\
[dim]╭───────────────────────────────────────────────────────────────────╮[/dim]
[dim]│[/dim] [bold cyan]🤖 AI CLI — Slash Commands[/bold cyan] [dim](type a command or just start chatting)[/dim]
[dim]╰───────────────────────────────────────────────────────────────────╯[/dim]

  [bold yellow]📦 Session[/bold yellow]
  /help                       show this help
  /info                       session overview (model, provider, tools, config)
  /clear                      clear conversation history
  /history                    show recent messages with truncation
  /count                      show message count
  /usage                      show token usage for this session
  /retry                      re-send the last user message
  /compact                    summarize & compact conversation history

  [bold yellow]🧠 Models[/bold yellow]
  /model [name]               show or switch the active model
  /models                     list all configured models in a table
  /system <prompt>            change the system prompt for this session
  /config                     show current configuration summary
  /temperature <0-2>           set sampling temperature (if supported)
  /maxtokens <n>              set max output tokens for this session

  [bold yellow]🔧 Tools & MCP[/bold yellow]
  /tools                      list all available tools (built-in + MCP)
  /mcp                        list connected MCP servers with tool counts
  /mcp reconnect               reconnect to all MCP servers
  /tools toggle <name>        enable/disable a specific tool

  [bold yellow]💾 Sessions[/bold yellow]
  /save [name]                save the current conversation
  /load <name>                load a previously saved conversation
  /sessions                   list saved conversations
  /delete <name>              delete a saved session
  /rename <new>               rename the current session

  [bold yellow]🖥️ Output[/bold yellow]
  /stream on|off               toggle streaming output
  /markdown on|off             toggle markdown rendering
  /width <n>                  set console output width (0 = auto)

  [bold yellow]⚙️ Settings[/bold yellow]
  /set <key> <value>           set a config value at runtime
  /shell on|off                toggle shell command execution
  /confirm on|off              toggle write/shell confirmation prompts

  [bold yellow]📋 Misc[/bold yellow]
  /copy                       copy last AI response to clipboard
  /export [format]            export conversation (txt, json, markdown)
  /theme                      show current UI theme info
  /time                       show current time and session duration
  /version                    show version info
  /exit, /quit                leave

[dim]💡 Tip: Up/down arrows cycle through input history. Ctrl+C to cancel.[/dim]
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
            enable_tool_creator=tool_cfg.get("enable_tool_creator", False),
            confirm_before_tool_creator=tool_cfg.get("confirm_before_tool_creator", True),
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
        from . import __version__
        self.console.print(
            Panel.fit(
                f"[bold cyan]🤖 AI CLI Assistant[/bold cyan]  [dim]v{__version__}[/dim]\n"
                f"[dim]┌[/dim]─ model:   [green]{self.model_name}[/green] [dim]({self.session.provider.name})[/dim]\n"
                f"[dim]├[/dim]─ tools:   [yellow]{len(self.tools.names())}[/yellow]   mcp: [blue]{len(self.mcp_manager.list_server_names())}[/blue] servers\n"
                f"[dim]├[/dim]─ stream:  {'[green]on[/green]' if self.stream else '[red]off[/red]'}   markdown: {'[green]on[/green]' if self.cfg.get('ui', {}).get('markdown', True) else '[red]off[/red]'}\n"
                f"[dim]└[/dim]─ session: [italic]{self.session.name or '(unnamed)'}[/italic]\n"
                f"[dim]💡 Type /help for commands, /exit to quit[/dim]",
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
            self.console.print("[dim]Goodbye! 👋[/dim]")
            return True
        if cmd == "help":
            self.console.print(HELP_TEXT)
        elif cmd == "info":
            self._cmd_info()
        elif cmd == "model":
            if arg:
                self._switch_model(arg)
            else:
                self.console.print(f"current model: [green]{self.model_name}[/green] ({self.session.provider.name})")
        elif cmd == "models":
            self._cmd_models()
        elif cmd == "system":
            if arg:
                self.session.system_prompt = arg
                self.console.print("[green]✓[/green] system prompt updated")
            else:
                self.console.print(Panel(self.session.system_prompt or "[dim](empty)[/dim]", title="system prompt"))
        elif cmd == "config":
            self._cmd_config()
        elif cmd == "tools":
            if arg.startswith("toggle "):
                self._cmd_tools_toggle(arg[7:].strip())
            else:
                self._cmd_tools()
        elif cmd == "mcp":
            if arg == "reconnect":
                self._cmd_mcp_reconnect()
            else:
                self._cmd_mcp()
        elif cmd == "save":
            self.session.name = arg or self.session.name
            path = self.session.save()
            self.console.print(f"[green]✓[/green] saved to {path}")
        elif cmd == "load":
            self._load_session(arg)
        elif cmd == "sessions":
            self._cmd_sessions()
        elif cmd == "delete":
            self._cmd_delete_session(arg)
        elif cmd == "rename":
            self._cmd_rename_session(arg)
        elif cmd == "usage":
            self._cmd_usage()
        elif cmd == "clear":
            self.session.messages.clear()
            self.console.print("[green]✓[/green] conversation cleared")
        elif cmd == "history":
            self._cmd_history()
        elif cmd == "count":
            self._cmd_count()
        elif cmd == "stream":
            if arg in ("on", "off"):
                self.stream = arg == "on"
                self.console.print(f"[green]✓[/green] streaming {'enabled' if self.stream else 'disabled'}")
            else:
                self.console.print("usage: /stream on|off")
        elif cmd == "markdown":
            if arg in ("on", "off"):
                self.cfg.setdefault("ui", {})["markdown"] = arg == "on"
                self.console.print(f"[green]✓[/green] markdown {'enabled' if arg == 'on' else 'disabled'}")
            else:
                self.console.print("usage: /markdown on|off")
        elif cmd == "retry":
            self._cmd_retry()
        elif cmd == "compact":
            self._cmd_compact()
        elif cmd == "temperature":
            self._cmd_temperature(arg)
        elif cmd == "maxtokens":
            self._cmd_maxtokens(arg)
        elif cmd == "width":
            self._cmd_width(arg)
        elif cmd == "set":
            self._cmd_set(arg)
        elif cmd == "shell":
            if arg in ("on", "off"):
                self.cfg.setdefault("tools", {})["enable_shell"] = arg == "on"
                self.console.print(f"[green]✓[/green] shell execution {'enabled' if arg == 'on' else 'disabled'}")
            else:
                self.console.print("usage: /shell on|off")
        elif cmd == "confirm":
            if arg in ("on", "off"):
                val = arg == "on"
                self.cfg.setdefault("tools", {})["confirm_before_write"] = val
                self.cfg.setdefault("tools", {})["confirm_before_shell"] = val
                self.console.print(f"[green]✓[/green] confirmation prompts {'enabled' if val else 'disabled'}")
            else:
                self.console.print("usage: /confirm on|off")
        elif cmd == "copy":
            self._cmd_copy()
        elif cmd == "export":
            self._cmd_export(arg)
        elif cmd == "theme":
            self._cmd_theme()
        elif cmd == "time":
            self._cmd_time()
        elif cmd == "version":
            from . import __version__
            self.console.print(f"[bold cyan]ai-cli-assistant[/bold cyan] v[green]{__version__}[/green]")
        else:
            self.console.print(f"[red]unknown command:[/red] /{cmd}  [dim](try /help)[/dim]")
        return False

    def _switch_model(self, name: str) -> None:
        if name not in self.cfg.get("models", {}):
            self.console.print(f"[red]✗ unknown model '{name}'.[/red] [dim]see /models[/dim]")
            return
        try:
            old_messages = self.session.messages
            self.model_name = name
            self.session = self._new_session()
            self.session.messages = old_messages
            self.console.print(f"[green]✓[/green] switched to [green]{name}[/green]")
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
        self.console.print(f"[green]✓[/green] loaded '{name}' [dim]({len(self.session.messages)} messages)[/dim]")

    # -- new command implementations ----------------------------------------

    def _cmd_info(self) -> None:
        """Show a summary of the current session state."""
        s = self.session.stats
        info_lines = [
            f"[bold cyan]🧠 Model[/bold cyan]       [green]{self.model_name}[/green] [dim]({self.session.provider.name})[/dim]",
            f"[bold cyan]📦 Provider[/bold cyan]    {self.session.provider.model}",
            f"[bold cyan]🔧 Tools[/bold cyan]       [yellow]{len(self.tools.names())}[/yellow] [dim]({len(self.mcp_manager.list_server_names())} MCP servers)[/dim]",
            f"[bold cyan]💬 Messages[/bold cyan]    {len(self.session.messages)}",
            f"[bold cyan]🔄 Turns[/bold cyan]       {s.turns}",
            f"[bold cyan]📊 Tokens[/bold cyan]      [dim]in:[/dim] {s.total_input_tokens:,}  [dim]out:[/dim] {s.total_output_tokens:,}  [dim]total:[/dim] {s.total_input_tokens + s.total_output_tokens:,}",
            f"[bold cyan]🖥️ Stream[/bold cyan]      {'[green]on[/green]' if self.stream else '[red]off[/red]'}",
            f"[bold cyan]📝 Markdown[/bold cyan]    {'[green]on[/green]' if self.cfg.get('ui', {}).get('markdown', True) else '[red]off[/red]'}",
            f"[bold cyan]💾 Session[/bold cyan]     [italic]{self.session.name or '(unnamed)'}[/italic]",
        ]
        self.console.print(Panel("\n".join(info_lines), title="[bold cyan]📋 Session Info[/bold cyan]", border_style="cyan", padding=(1, 2)))

    def _cmd_models(self) -> None:
        """List configured models in a rich table."""
        table = Table(title="🧠 Configured Models", show_header=True, header_style="bold cyan", border_style="dim", show_lines=True)
        table.add_column("", width=3)
        table.add_column("Name", style="bold")
        table.add_column("Provider", style="blue")
        table.add_column("Model ID", style="dim")
        table.add_column("Base URL", style="dim")
        for name, spec in self.cfg.get("models", {}).items():
            marker = "[green]★[/green]" if name == self.model_name else "[dim]○[/dim]"
            base_url = spec.get("base_url", "[dim]default[/dim]")
            table.add_row(marker, name, spec["provider"], spec["model"], base_url)
        self.console.print(table)
        self.console.print(f"\n[dim]💡 Switch with: /model <name>[/dim]")

    def _cmd_tools(self) -> None:
        """List all available tools in a rich table."""
        specs = self.tools.all_specs()
        if not specs:
            self.console.print("[dim]No tools available.[/dim]")
            return
        table = Table(title=f"🔧 Available Tools ({len(specs)})", show_header=True, header_style="bold yellow", border_style="dim", show_lines=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("Name", style="bold", min_width=20)
        table.add_column("Source", style="cyan", width=10)
        table.add_column("Description", style="dim", ratio=1)
        for i, spec in enumerate(specs, 1):
            source = "MCP" if spec.name.startswith("mcp__") else "built-in"
            source_style = "blue" if source == "MCP" else "green"
            desc = spec.description or ""
            if len(desc) > 100:
                desc = desc[:97] + "..."
            table.add_row(str(i), spec.name, f"[{source_style}]{source}[/{source_style}]", desc)
        self.console.print(table)
        self.console.print(f"\n[dim]💡 Use /tools toggle <name> to enable/disable a tool[/dim]")

    def _cmd_mcp(self) -> None:
        """List connected MCP servers with tool counts."""
        names = self.mcp_manager.list_server_names()
        if not names:
            self.console.print("[dim]No MCP servers connected.[/dim]")
            self.console.print("[dim]💡 Run `ai mcp list` to browse and add MCP servers[/dim]")
            return
        table = Table(title=f"🔗 Connected MCP Servers ({len(names)})", show_header=True, header_style="bold blue", border_style="dim", show_lines=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("Name", style="bold")
        table.add_column("Tools", justify="right", style="yellow")
        table.add_column("Tool Names", style="dim", ratio=1)
        mcp_specs = [s for s in self.tools.all_specs() if s.name.startswith("mcp__")]
        for i, name in enumerate(names, 1):
            server_tools = [s.name.split("__", 2)[-1] for s in mcp_specs if s.name.split("__")[1] == name]
            tool_count = len(server_tools)
            tool_preview = ", ".join(server_tools[:5])
            if len(server_tools) > 5:
                tool_preview += f"... (+{len(server_tools) - 5})"
            table.add_row(str(i), name, str(tool_count), tool_preview)
        self.console.print(table)
        self.console.print(f"\n[dim]💡 Use /mcp reconnect to reconnect to all servers[/dim]")

    def _cmd_sessions(self) -> None:
        """List saved sessions in a table."""
        names = Session.list_saved()
        if not names:
            self.console.print("[dim]No saved sessions.[/dim]")
            self.console.print("[dim]💡 Use /save <name> to save the current conversation[/dim]")
            return
        table = Table(title=f"💾 Saved Sessions ({len(names)})", show_header=True, header_style="bold green", border_style="dim")
        table.add_column("#", style="dim", width=4)
        table.add_column("Name", style="bold")
        table.add_column("Status", style="dim", width=12)
        for i, name in enumerate(names, 1):
            status = "[green]★ current[/green]" if name == self.session.name else "[dim]saved[/dim]"
            table.add_row(str(i), name, status)
        self.console.print(table)
        self.console.print(f"\n[dim]💡 /load <name> to load · /delete <name> to remove[/dim]")

    def _cmd_usage(self) -> None:
        """Show token usage in a panel."""
        s = self.session.stats
        total = s.total_input_tokens + s.total_output_tokens
        self.console.print(
            Panel(
                f"  [bold]Turns[/bold]            [yellow]{s.turns}[/yellow]\n"
                f"  [bold]Input tokens[/bold]     [green]{s.total_input_tokens:,}[/green]\n"
                f"  [bold]Output tokens[/bold]    [blue]{s.total_output_tokens:,}[/blue]\n"
                f"  [bold]Total tokens[/bold]      [bold]{total:,}[/bold]",
                title="[bold cyan]📊 Token Usage[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    def _cmd_history(self) -> None:
        """Show recent messages in the conversation."""
        msgs = self.session.messages
        if not msgs:
            self.console.print("[dim]No messages yet.[/dim]")
            return
        self.console.print(Panel(f"[bold]💬 Conversation History[/bold] ({len(msgs)} messages)", border_style="dim"))
        for i, msg in enumerate(msgs, 1):
            role = msg.get("role", "?")
            content = msg.get("content", "")
            # Extract text from content blocks
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif isinstance(block, dict) and block.get("type") == "tool_use":
                        text_parts.append(f"[🔧 tool: {block.get('name', '?')}]")
                    elif isinstance(block, dict) and block.get("type") == "tool_result":
                        text_parts.append(f"[✅ tool_result]")
                text = " ".join(text_parts)
            elif isinstance(content, str):
                text = content
            else:
                text = str(content)
            # Truncate long messages
            if len(text) > 200:
                text = text[:197] + "..."
            role_label = {"user": "🧑 user", "assistant": "🤖 assistant"}.get(role, role)
            role_color = {"user": "blue", "assistant": "green"}.get(role, "yellow")
            self.console.print(f"  [dim]{i:>3}.[/dim] [{role_color}]{role_label}[/{role_color}]: {text}")

    def _cmd_count(self) -> None:
        """Show message count."""
        count = len(self.session.messages)
        self.console.print(f"messages: [bold]{count}[/bold]")

    def _cmd_config(self) -> None:
        """Show current configuration summary."""
        ui = self.cfg.get("ui", {})
        tools = self.cfg.get("tools", {})
        bots = self.cfg.get("bots", {})
        lines = [
            f"[bold cyan]⚙️ Configuration[/bold cyan]",
            f"",
            f"[bold]Default model[/bold]   [green]{self.cfg.get('default_model', '?')}[/green]",
            f"[bold]Stream[/bold]          {'[green]on[/green]' if self.stream else '[red]off[/red]'}",
            f"[bold]Markdown[/bold]        {'[green]on[/green]' if ui.get('markdown', True) else '[red]off[/red]'}",
            f"[bold]Config path[/bold]     [dim]{cfgmod.CONFIG_PATH}[/dim]",
            f"[bold]MCP config[/bold]      [dim]{cfgmod.MCP_SERVERS_PATH}[/dim]",
            f"[bold]Sessions dir[/bold]    [dim]{cfgmod.SESSIONS_DIR}[/dim]",
            f"",
            f"[bold yellow]🔧 Tools[/bold yellow]",
            f"  filesystem:    {'[green]✓ on[/green]' if tools.get('enable_filesystem') else '[red]✗ off[/red]'}",
            f"  shell:         {'[green]✓ on[/green]' if tools.get('enable_shell') else '[red]✗ off[/red]'}",
            f"  http:          {'[green]✓ on[/green]' if tools.get('enable_http') else '[red]✗ off[/red]'}",
            f"  tool_creator:  {'[green]✓ on[/green]' if tools.get('enable_tool_creator') else '[red]✗ off[/red]'}",
            f"  confirm write: {'[green]✓ yes[/green]' if tools.get('confirm_before_write') else '[dim]no[/dim]'}",
            f"  confirm shell: {'[green]✓ yes[/green]' if tools.get('confirm_before_shell') else '[dim]no[/dim]'}",
            f"",
            f"[bold magenta]🤖 Bots[/bold magenta]",
            f"  telegram:      {'[green]✓ enabled[/green]' if bots.get('telegram', {}).get('enabled') else '[dim]✗ disabled[/dim]'}",
            f"  discord:        {'[green]✓ enabled[/green]' if bots.get('discord', {}).get('enabled') else '[dim]✗ disabled[/dim]'}",
        ]
        self.console.print(Panel("\n".join(lines), title="[bold cyan]📋 Configuration[/bold cyan]", border_style="cyan", padding=(1, 2)))

    def _cmd_retry(self) -> None:
        """Re-send the last user message."""
        # Find the last user message
        last_user_text = None
        for msg in reversed(self.session.messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            last_user_text = block["text"]
                            break
                elif isinstance(content, str):
                    last_user_text = content
                if last_user_text:
                    break
        if not last_user_text:
            self.console.print("[yellow]No previous user message to retry.[/yellow]")
            return
        # Remove the last user message and any assistant response after it
        # so we get a clean re-run
        while self.session.messages:
            last = self.session.messages[-1]
            if last.get("role") == "user":
                self.session.messages.pop()
                break
            self.session.messages.pop()
        self.console.print("[dim]↻ retrying last message...[/dim]")
        self._handle_message(last_user_text)

    # -- additional command implementations ---------------------------------

    def _cmd_compact(self) -> None:
        """Summarize and compact conversation history to save tokens."""
        msgs = self.session.messages
        if len(msgs) < 6:
            self.console.print("[yellow]Not enough messages to compact (need at least 6).[/yellow]")
            return
        # Keep the last 2 messages, summarize the rest
        to_summarize = msgs[:-2]
        keep = msgs[-2:]
        # Build a summary of old messages
        summary_parts = []
        for msg in to_summarize:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif isinstance(block, dict) and block.get("type") == "tool_use":
                        text_parts.append(f"[used tool: {block.get('name', '?')}]")
                    elif isinstance(block, dict) and block.get("type") == "tool_result":
                        text_parts.append(f"[tool result received]")
                text = " ".join(text_parts)
            elif isinstance(content, str):
                text = content
            else:
                text = str(content)
            if len(text) > 150:
                text = text[:147] + "..."
            summary_parts.append(f"{role}: {text}")
        summary = "\n".join(summary_parts)
        compact_msg = {
            "role": "user",
            "content": [{
                "type": "text",
                "text": f"[Previous conversation summary — {len(to_summarize)} messages compacted]\n{summary}"
            }]
        }
        self.session.messages = [compact_msg] + keep
        self.console.print(
            f"[green]✓[/green] compacted {len(to_summarize)} messages into 1 summary. "
            f"[dim]({len(self.session.messages)} messages now)[/dim]"
        )

    def _cmd_temperature(self, arg: str) -> None:
        """Set sampling temperature."""
        if not arg:
            current = self.cfg.get("provider_options", {}).get(
                self.session.provider.name, {}
            ).get("temperature", "[dim]default[/dim]")
            self.console.print(f"temperature: {current}")
            return
        try:
            val = float(arg)
        except ValueError:
            self.console.print("[red]Invalid value. Usage: /temperature <0-2>[/red]")
            return
        if not (0.0 <= val <= 2.0):
            self.console.print("[red]Temperature must be between 0 and 2.[/red]")
            return
        provider_key = self.session.provider.name
        self.cfg.setdefault("provider_options", {}).setdefault(provider_key, {})["temperature"] = val
        self.console.print(f"[green]✓[/green] temperature set to {val}")

    def _cmd_maxtokens(self, arg: str) -> None:
        """Set max output tokens."""
        if not arg:
            current = self.cfg.get("provider_options", {}).get(
                self.session.provider.name, {}
            ).get("max_tokens", "[dim]default[/dim]")
            self.console.print(f"max tokens: {current}")
            return
        try:
            val = int(arg)
        except ValueError:
            self.console.print("[red]Invalid value. Usage: /maxtokens <n>[/red]")
            return
        if val < 1:
            self.console.print("[red]Max tokens must be a positive integer.[/red]")
            return
        provider_key = self.session.provider.name
        self.cfg.setdefault("provider_options", {}).setdefault(provider_key, {})["max_tokens"] = val
        self.console.print(f"[green]✓[/green] max tokens set to {val:,}")

    def _cmd_width(self, arg: str) -> None:
        """Set console output width."""
        if not arg:
            self.console.print(f"console width: {self.console.width}")
            return
        try:
            val = int(arg)
        except ValueError:
            self.console.print("[red]Invalid value. Usage: /width <n> (0 = auto)[/red]")
            return
        if val == 0:
            self.console.width = None  # auto
            self.console.print("[green]✓[/green] console width set to auto")
        else:
            self.console.width = val
            self.console.print(f"[green]✓[/green] console width set to {val}")

    def _cmd_set(self, arg: str) -> None:
        """Set a config value at runtime."""
        if not arg:
            self.console.print("[dim]usage: /set <key> <value>[/dim]")
            self.console.print("[dim]keys: stream, markdown, show_token_usage[/dim]")
            return
        parts = arg.split(maxsplit=1)
        if len(parts) < 2:
            self.console.print("[red]usage: /set <key> <value>[/red]")
            return
        key, value = parts[0].strip(), parts[1].strip()
        if key in ("stream", "markdown", "show_token_usage"):
            if value.lower() in ("on", "true", "1", "yes"):
                self.cfg.setdefault("ui", {})[key] = True
                if key == "stream":
                    self.stream = True
                self.console.print(f"[green]✓[/green] {key} = on")
            elif value.lower() in ("off", "false", "0", "no"):
                self.cfg.setdefault("ui", {})[key] = False
                if key == "stream":
                    self.stream = False
                self.console.print(f"[green]✓[/green] {key} = off")
            else:
                self.console.print("[red]value must be on/off, true/false, 1/0[/red]")
        else:
            self.console.print(f"[red]unknown key '{key}'.[/red] available: stream, markdown, show_token_usage")

    def _cmd_copy(self) -> None:
        """Copy the last AI response to clipboard."""
        last_assistant_text = None
        for msg in reversed(self.session.messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block["text"])
                    last_assistant_text = "\n".join(text_parts) if text_parts else None
                elif isinstance(content, str):
                    last_assistant_text = content
                if last_assistant_text:
                    break
        if not last_assistant_text:
            self.console.print("[yellow]No AI response to copy.[/yellow]")
            return
        try:
            import subprocess
            subprocess.run(["pbcopy"], input=last_assistant_text, text=True, timeout=5)
            self.console.print(f"[green]✓[/green] copied {len(last_assistant_text)} chars to clipboard")
        except FileNotFoundError:
            try:
                import subprocess
                subprocess.run(["xclip", "-selection", "clipboard"], input=last_assistant_text, text=True, timeout=5)
                self.console.print(f"[green]✓[/green] copied {len(last_assistant_text)} chars to clipboard")
            except FileNotFoundError:
                try:
                    import subprocess
                    subprocess.run(["clip.exe"], input=last_assistant_text, text=True, timeout=5)
                    self.console.print(f"[green]✓[/green] copied {len(last_assistant_text)} chars to clipboard")
                except FileNotFoundError:
                    self.console.print("[yellow]No clipboard utility found (pbcopy/xclip/clip.exe).[/yellow]")
        except Exception as e:
            self.console.print(f"[red]Failed to copy: {e}[/red]")

    def _cmd_export(self, arg: str) -> None:
        """Export the conversation to a file."""
        fmt = arg or "txt"
        if fmt not in ("txt", "json", "markdown", "md"):
            self.console.print("[red]format must be: txt, json, or markdown[/red]")
            return
        if not self.session.messages:
            self.console.print("[yellow]No messages to export.[/yellow]")
            return
        import time as _time
        timestamp = _time.strftime("%Y%m%d_%H%M%S")
        export_dir = cfgmod.SESSIONS_DIR / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            import json
            path = export_dir / f"export_{timestamp}.json"
            data = self.session.to_dict()
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        elif fmt in ("markdown", "md"):
            path = export_dir / f"export_{timestamp}.md"
            lines = [f"# Conversation Export\n\n"]
            lines.append(f"_Exported: {_time.strftime('%Y-%m-%d %H:%M:%S')}_\n")
            lines.append(f"_Model: {self.model_name} ({self.session.provider.name})_\n\n---\n")
            for msg in self.session.messages:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block["text"])
                        elif isinstance(block, dict) and block.get("type") == "tool_use":
                            text_parts.append(f"*[tool: {block.get('name', '?')}]*")
                    text = "\n".join(text_parts)
                elif isinstance(content, str):
                    text = content
                else:
                    text = str(content)
                role_label = {"user": "🧑 User", "assistant": "🤖 Assistant"}.get(role, role)
                lines.append(f"\n### {role_label}\n\n{text}\n")
            with open(path, "w") as f:
                f.write("\n".join(lines))
        else:
            path = export_dir / f"export_{timestamp}.txt"
            lines = []
            for msg in self.session.messages:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block["text"])
                    text = " ".join(text_parts)
                elif isinstance(content, str):
                    text = content
                else:
                    text = str(content)
                lines.append(f"[{role}] {text}\n")
            with open(path, "w") as f:
                f.write("\n".join(lines))
        self.console.print(f"[green]✓[/green] exported {len(self.session.messages)} messages to {path}")

    def _cmd_theme(self) -> None:
        """Show current UI theme info."""
        self.console.print(
            Panel(
                f"[bold]Console width[/bold]    {self.console.width}\n"
                f"[bold]Color system[/bold]    {self.console.color_system}\n"
                f"[bold]Terminal[/bold]        {self.console.is_terminal}\n"
                f"[bold]Encoding[/bold]        {self.console.encoding}\n"
                f"[bold]Stream[/bold]          {'on' if self.stream else 'off'}\n"
                f"[bold]Markdown[/bold]        {'on' if self.cfg.get('ui', {}).get('markdown', True) else 'off'}",
                title="[cyan]UI Info[/cyan]",
                border_style="cyan",
            )
        )

    def _cmd_time(self) -> None:
        """Show current time and session duration."""
        import time as _time
        now = _time.strftime("%Y-%m-%d %H:%M:%S")
        msg_count = len(self.session.messages)
        self.console.print(
            Panel(
                f"[bold]Current time[/bold]     {now}\n"
                f"[bold]Messages[/bold]         {msg_count}\n"
                f"[bold]Turns[/bold]            {self.session.stats.turns}\n"
                f"[bold]Total tokens[/bold]     {self.session.stats.total_input_tokens + self.session.stats.total_output_tokens:,}",
                title="[cyan]⏱ Session Time[/cyan]",
                border_style="cyan",
            )
        )

    def _cmd_delete_session(self, name: str) -> None:
        """Delete a saved session."""
        if not name:
            self.console.print("usage: /delete <name>")
            return
        path = cfgmod.SESSIONS_DIR / f"{name}.json"
        if not path.exists():
            self.console.print(f"[red]No saved session named '{name}'.[/red]")
            return
        path.unlink()
        self.console.print(f"[green]✓[/green] deleted session '{name}'")

    def _cmd_rename_session(self, new_name: str) -> None:
        """Rename the current session."""
        if not new_name:
            self.console.print("usage: /rename <new_name>")
            return
        old_name = self.session.name
        self.session.name = new_name
        self.console.print(f"[green]✓[/green] renamed session '{old_name or '(unnamed)'}' → '{new_name}'")

    def _cmd_mcp_reconnect(self) -> None:
        """Reconnect to all MCP servers."""
        self.console.print("[dim]Disconnecting from MCP servers...[/dim]")
        self.mcp_manager.disconnect_all()
        # Create a fresh manager
        self.mcp_manager = MCPManager()
        self.tools.set_mcp_manager(self.mcp_manager)
        servers = cfgmod.load_mcp_servers()
        if servers:
            self.console.print("[dim]Reconnecting to MCP servers...[/dim]")
            self.mcp_manager.connect_all(servers)
        self.console.print(
            f"[green]✓[/green] reconnected: "
            f"[blue]{len(self.mcp_manager.list_server_names())}[/blue] servers, "
            f"[yellow]{len(self.tools.names())}[/yellow] tools"
        )

    def _cmd_tools_toggle(self, name: str) -> None:
        """Enable/disable a specific tool (basic toggle for local tools)."""
        if not name:
            self.console.print("usage: /tools toggle <name>")
            return
        all_names = self.tools.names()
        if name not in all_names:
            self.console.print(f"[red]Tool '{name}' not found.[/red] available: {', '.join(all_names[:10])}{'...' if len(all_names) > 10 else ''}")
            return
        if name in self.tools._local:
            spec, handler = self.tools._local[name]
            if handler is None:
                self.console.print(f"[yellow]Tool '{name}' is already disabled.[/yellow]")
                return
            # Disable by setting handler to None (won't be listed in specs)
            self.tools._local[name] = (spec, None)
            self.console.print(f"[yellow]✓[/yellow] disabled tool '{name}'")
        else:
            self.console.print(f"[yellow]Cannot toggle MCP tool '{name}' (managed by MCP server).[/yellow]")

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
            self.console.print(f"\n[yellow]🔧 → calling[/yellow] [bold]{name}[/bold]({args})")

        def on_tool_result(name: str, output: str, is_error: bool) -> None:
            color = "red" if is_error else "green"
            icon = "❌" if is_error else "✅"
            preview = output if len(output) < 300 else output[:300] + "..."
            self.console.print(f"  [{color}]{icon} {name}[/{color}] {preview}")

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
