from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from . import config as cfgmod
from .mcp.manager import MCPManager
from .providers import ProviderError, build_provider
from .repl import REPL
from .session import Session
from .tools.registry import ToolRegistry

BOTS_USAGE = (
    "Usage:\n"
    "  ai bots setup [telegram|discord]   interactive token/permissions setup\n"
    "  ai bots run   [telegram|discord|all]   start a bot (blocks until Ctrl+C)\n"
    "  ai bots status                     show which bots are configured"
)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ai",
        description="A multi-model, MCP-aware, tool-calling AI assistant for your terminal.",
        epilog=(
            "Also available:\n"
            "  ai setup                run the interactive setup wizard\n"
            "  ai bots setup|run ...   configure and run Telegram/Discord bots\n"
            "See README.md for details."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("prompt", nargs="*", help="One-shot prompt. If omitted, starts the interactive REPL.")
    p.add_argument("-m", "--model", help="Model to use (see `ai --list-models`).")
    p.add_argument("--system", help="Override the system prompt for this run.")
    p.add_argument("--config", type=Path, help="Path to a config.yaml file.")
    p.add_argument("--mcp-config", type=Path, help="Path to an mcp_servers.json file.")
    p.add_argument("--no-mcp", action="store_true", help="Skip connecting to MCP servers.")
    p.add_argument("--no-stream", action="store_true", help="Disable streaming output.")
    p.add_argument("--no-tools", action="store_true", help="Disable all tool calling for this run.")
    p.add_argument("--list-models", action="store_true", help="List configured models and exit.")
    p.add_argument("--init", action="store_true", help="Write a bare default config to ~/.ai-cli and exit (no prompts).")
    p.add_argument("--setup", action="store_true", help="Run the interactive setup wizard.")
    p.add_argument("--load", metavar="NAME", help="Load a saved session before starting.")
    return p


def main(argv=None) -> int:
    console = Console()
    argv = list(sys.argv[1:] if argv is None else argv)

    # ~/.ai-cli/.env holds API keys and bot tokens saved by the wizard --
    # load it before anything looks up an environment variable.
    cfgmod.load_env_file()

    # "ai bots ..." and "ai setup" are separate mini command-lines, handled
    # before argparse ever sees them (argparse's single positional `prompt`
    # would otherwise happily swallow "bots run telegram" as a literal
    # one-shot prompt).
    if argv and argv[0] == "bots":
        return _handle_bots(console, argv[1:])
    if argv and argv[0] == "setup":
        from .wizard import run_setup_wizard

        run_setup_wizard(console)
        return 0

    args = build_arg_parser().parse_args(argv)

    if args.init:
        cfgmod.write_default_config_if_missing()
        console.print(f"[green]Initialized config at {cfgmod.APP_DIR}[/green]")
        console.print(f"  edit {cfgmod.CONFIG_PATH} for models/tool settings")
        console.print(f"  edit {cfgmod.MCP_SERVERS_PATH} to add MCP servers")
        console.print("  or run `ai --setup` for a guided walkthrough instead")
        return 0

    if args.setup:
        from .wizard import run_setup_wizard

        run_setup_wizard(console)
        return 0

    cfg_path = args.config or cfgmod.CONFIG_PATH
    first_run = not cfg_path.exists()
    if first_run and not args.list_models:
        console.print("[cyan]No configuration found yet -- let's get you set up.[/cyan]\n")
        from .wizard import run_setup_wizard

        cfg = run_setup_wizard(console)
        console.print()
    else:
        cfg = cfgmod.load_config(args.config)

    if args.list_models:
        for name, spec in cfg.get("models", {}).items():
            extra = f" base_url={spec['base_url']}" if "base_url" in spec else ""
            console.print(f"{name}  [dim]({spec['provider']}: {spec['model']}{extra})[/dim]")
        return 0

    model_name = args.model or cfg.get("default_model")
    if args.system:
        cfg["default_system_prompt"] = args.system
    if args.no_tools:
        cfg["tools"] = {k: False for k in cfg.get("tools", {})}
    if args.no_stream:
        cfg.setdefault("ui", {})["stream"] = False

    if args.prompt:
        return _run_one_shot(console, cfg, model_name, " ".join(args.prompt), args)

    try:
        repl = REPL(cfg, model_name, mcp_config_path=args.mcp_config, no_mcp=args.no_mcp)
    except ProviderError as e:
        console.print(f"[red]{e}[/red]")
        return 1
    if args.load:
        repl._load_session(args.load)  # noqa: SLF001 -- fine, same module family
    repl.run()
    return 0


def _run_one_shot(console: Console, cfg, model_name: str, prompt: str, args) -> int:
    """Non-interactive mode: `ai "what's 2+2"` answers once and exits."""
    mcp_manager = MCPManager()
    tools = ToolRegistry(mcp_manager)
    tool_cfg = cfg.get("tools", {})
    tools.register_builtin(
        enable_filesystem=tool_cfg.get("enable_filesystem", True),
        enable_shell=tool_cfg.get("enable_shell", False),
        enable_http=tool_cfg.get("enable_http", True),
        confirm_before_write=tool_cfg.get("confirm_before_write", True),
        confirm_before_shell=tool_cfg.get("confirm_before_shell", True),
        confirm_fn=lambda msg: _cli_confirm(console, msg),
    )
    if not args.no_mcp:
        servers = cfgmod.load_mcp_servers(args.mcp_config)
        if servers:
            mcp_manager.connect_all(servers, quiet=True)

    try:
        provider = build_provider(model_name, cfg)
    except ProviderError as e:
        console.print(f"[red]{e}[/red]")
        return 1

    session = Session(provider=provider, system_prompt=cfg.get("default_system_prompt", ""), tools=tools)
    if args.load:
        try:
            data = Session.load_messages(args.load)
            session.messages = data["messages"]
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            return 1

    stream = cfg.get("ui", {}).get("stream", True)
    buffer = {"text": ""}

    def on_text(chunk: str) -> None:
        buffer["text"] += chunk
        if stream:
            console.print(chunk, end="")

    def on_tool_call(name: str, tool_args: dict) -> None:
        console.print(f"[yellow]-> {name}[/yellow]({tool_args})", file=sys.stderr)

    def on_tool_result(name: str, output: str, is_error: bool) -> None:
        color = "red" if is_error else "green"
        console.print(f"[{color}]<- {name}[/{color}]", file=sys.stderr)

    try:
        session.run_turn(prompt, on_text, on_tool_call, on_tool_result, stream=stream)
    except ProviderError as e:
        console.print(f"[red]{e}[/red]")
        return 1
    finally:
        mcp_manager.disconnect_all()

    console.print()
    if not stream and cfg.get("ui", {}).get("markdown", True):
        console.print(Markdown(buffer["text"]))
    return 0


def _cli_confirm(console: Console, message: str) -> bool:
    console.print(f"[yellow]{message}[/yellow] [dim](y/N)[/dim]")
    answer = input("> ").strip().lower()
    return answer in ("y", "yes")


# -- `ai bots ...` -------------------------------------------------------------


def _handle_bots(console: Console, sub_argv: list) -> int:
    if not sub_argv:
        console.print(BOTS_USAGE)
        return 1

    action = sub_argv[0]
    target = sub_argv[1] if len(sub_argv) > 1 else None
    cfg = cfgmod.load_config()

    if action == "setup":
        from . import wizard

        if target == "telegram":
            wizard._setup_telegram(console, cfg)  # noqa: SLF001
            cfgmod.save_config(cfg)
        elif target == "discord":
            wizard._setup_discord(console, cfg)  # noqa: SLF001
            cfgmod.save_config(cfg)
        elif target is None:
            if _ask_yes_no(console, "Set up Telegram?"):
                wizard._setup_telegram(console, cfg)  # noqa: SLF001
            if _ask_yes_no(console, "Set up Discord?"):
                wizard._setup_discord(console, cfg)  # noqa: SLF001
            cfgmod.save_config(cfg)
        else:
            console.print(f"[red]Unknown target '{target}'.[/red] {BOTS_USAGE}")
            return 1
        return 0

    if action == "status":
        for key in ("telegram", "discord"):
            bot_cfg = cfg["bots"][key]
            state = "[green]enabled[/green]" if bot_cfg.get("enabled") else "[dim]not configured[/dim]"
            model = bot_cfg.get("model") or f"(default: {cfg.get('default_model')})"
            console.print(f"{key}: {state}  model={model}")
        return 0

    if action == "run":
        if target == "telegram":
            return _run_telegram(console, cfg)
        if target == "discord":
            return _run_discord(console, cfg)
        if target == "all":
            return _run_all(console, cfg)
        console.print(f"[red]Unknown target '{target}'.[/red] {BOTS_USAGE}")
        return 1

    console.print(f"[red]Unknown action '{action}'.[/red]\n{BOTS_USAGE}")
    return 1


def _ask_yes_no(console: Console, question: str) -> bool:
    from rich.prompt import Confirm

    return Confirm.ask(question, default=False)


def _run_telegram(console: Console, cfg) -> int:
    from .bots.telegram_bot import TelegramBot, TelegramConfigError

    try:
        TelegramBot(cfg).run()
    except TelegramConfigError as e:
        console.print(f"[red]{e}[/red]")
        return 1
    return 0


def _run_discord(console: Console, cfg) -> int:
    from .bots.discord_bot import DiscordConfigError, run_discord_bot

    try:
        run_discord_bot(cfg)
    except DiscordConfigError as e:
        console.print(f"[red]{e}[/red]")
        return 1
    return 0


def _run_all(console: Console, cfg) -> int:
    tg_token = cfgmod.resolve_api_key(cfg["bots"]["telegram"].get("token_env", "TELEGRAM_BOT_TOKEN"))
    dc_token = cfgmod.resolve_api_key(cfg["bots"]["discord"].get("token_env", "DISCORD_BOT_TOKEN"))

    if tg_token and dc_token:
        from .bots.discord_bot import DiscordConfigError, run_discord_bot
        from .bots.telegram_bot import TelegramBot

        errors = []

        def _telegram_thread() -> None:
            try:
                TelegramBot(cfg).run()
            except Exception as e:  # noqa: BLE001
                errors.append(f"telegram crashed: {e}")

        t = threading.Thread(target=_telegram_thread, daemon=True)
        t.start()
        try:
            run_discord_bot(cfg)
        except DiscordConfigError as e:
            errors.append(str(e))
        except KeyboardInterrupt:
            pass
        for e in errors:
            console.print(f"[red]{e}[/red]")
        return 1 if errors else 0

    if tg_token:
        console.print("[dim]Discord not configured (run `ai bots setup discord`) -- starting Telegram only.[/dim]")
        return _run_telegram(console, cfg)

    if dc_token:
        console.print("[dim]Telegram not configured (run `ai bots setup telegram`) -- starting Discord only.[/dim]")
        return _run_discord(console, cfg)

    console.print("[red]Neither bot is configured.[/red] Run `ai bots setup` first.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
