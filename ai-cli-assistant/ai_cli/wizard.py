"""
First-run setup wizard. Walks through picking a default provider/model,
storing API keys in ~/.ai-cli/.env, tool permissions, and (optionally)
bot tokens for Telegram/Discord. Runs from the terminal -- bots never ask
for secrets over chat, they just point the owner back to this wizard.
"""

from __future__ import annotations

from typing import Any, Dict

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt

from . import config as cfgmod

PROVIDER_KEY_INFO = {
    "anthropic": ("ANTHROPIC_API_KEY", "https://console.anthropic.com/settings/keys"),
    "openai": ("OPENAI_API_KEY", "https://platform.openai.com/api-keys"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/keys"),
    "groq": ("GROQ_API_KEY", "https://console.groq.com/keys"),
    "together": ("TOGETHER_API_KEY", "https://api.together.ai/settings/api-keys"),
    "deepseek": ("DEEPSEEK_API_KEY", "https://platform.deepseek.com/api_keys"),
}

PROVIDER_LABELS = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (GPT)",
    "openrouter": "OpenRouter (many models, one key)",
    "groq": "Groq (fast open models, free tier)",
    "together": "Together AI",
    "deepseek": "DeepSeek",
    "ollama": "Ollama (local models, no key needed)",
}


def run_setup_wizard(console: Console = None) -> Dict[str, Any]:
    console = console or Console()
    console.print(
        Panel.fit(
            "[bold cyan]AI CLI Assistant -- first-run setup[/bold cyan]\n"
            "This will configure a default model, tool permissions, and\n"
            "(optionally) Telegram/Discord bots. You can re-run this any\n"
            "time with `ai --setup`, or edit ~/.ai-cli/config.yaml by hand.",
            border_style="cyan",
        )
    )

    cfg = cfgmod.load_config()

    # -- 1. pick a default provider + store its key -------------------------
    console.print("\n[bold]Step 1 -- pick a default provider[/bold]")
    provider_choices = list(PROVIDER_LABELS.keys())
    for i, key in enumerate(provider_choices, 1):
        console.print(f"  {i}. {PROVIDER_LABELS[key]}")
    idx = IntPrompt.ask("Choice", choices=[str(i) for i in range(1, len(provider_choices) + 1)], default=1)
    provider = provider_choices[idx - 1]

    if provider in PROVIDER_KEY_INFO:
        env_var, url = PROVIDER_KEY_INFO[provider]
        existing = cfgmod.resolve_api_key(env_var)
        if existing:
            console.print(f"[dim]{env_var} is already set in your environment -- keeping it.[/dim]")
        else:
            console.print(f"[dim]Get a key at {url}[/dim]")
            key_value = Prompt.ask(f"Paste your {env_var} (leave blank to skip for now)", password=True, default="")
            if key_value:
                cfgmod.set_env_var(env_var, key_value)
                console.print("[green]saved to ~/.ai-cli/.env[/green]")

    # pick / confirm the specific model for that provider
    candidate_models = [name for name, spec in cfg["models"].items() if spec["provider"] == provider]
    if candidate_models:
        console.print(f"\nModels available for {provider}: {', '.join(candidate_models)}")
        default_model = Prompt.ask("Default model", choices=candidate_models, default=candidate_models[0])
    else:
        default_model = Prompt.ask("Enter the exact model id to use", default="")
    cfg["default_model"] = default_model or cfg["default_model"]

    # -- 2. tool permissions -------------------------------------------------
    console.print("\n[bold]Step 2 -- tool permissions[/bold]")
    cfg["tools"]["enable_filesystem"] = Confirm.ask("Allow reading/writing local files?", default=True)
    cfg["tools"]["enable_http"] = Confirm.ask("Allow HTTP GET requests?", default=True)
    cfg["tools"]["enable_shell"] = Confirm.ask("Allow running shell commands? (powerful, be careful)", default=False)

    # -- 3. bots ---------------------------------------------------------------
    console.print("\n[bold]Step 3 -- bots (optional)[/bold]")
    if Confirm.ask("Set up a Telegram bot now?", default=False):
        _setup_telegram(console, cfg)
    if Confirm.ask("Set up a Discord bot now?", default=False):
        _setup_discord(console, cfg)

    cfg["setup_complete"] = True
    cfgmod.save_config(cfg)
    console.print(
        Panel.fit(
            f"[green]Setup complete.[/green] Config saved to {cfgmod.CONFIG_PATH}\n"
            f"Run `ai` to start chatting, or `ai bots run telegram|discord` to launch a bot.",
            border_style="green",
        )
    )
    return cfg


def _setup_telegram(console: Console, cfg: Dict[str, Any]) -> None:
    console.print(
        "[dim]Create a bot with @BotFather on Telegram, copy the token it gives you.[/dim]"
    )
    token = Prompt.ask("Telegram bot token", password=True, default="")
    if not token:
        console.print("[yellow]skipped[/yellow]")
        return
    cfgmod.set_env_var("TELEGRAM_BOT_TOKEN", token)
    owner = Prompt.ask(
        "Your numeric Telegram user id (optional -- restricts /admin commands; "
        "message @userinfobot to find it)",
        default="",
    )
    cfg["bots"]["telegram"]["enabled"] = True
    cfg["bots"]["telegram"]["owner_id"] = int(owner) if owner.strip().isdigit() else None
    console.print("[green]Telegram bot configured.[/green] Start it with: ai bots run telegram")


def _setup_discord(console: Console, cfg: Dict[str, Any]) -> None:
    console.print(
        "[dim]Create an application + bot at https://discord.com/developers/applications, "
        "copy the bot token, and enable 'Message Content Intent'.[/dim]"
    )
    token = Prompt.ask("Discord bot token", password=True, default="")
    if not token:
        console.print("[yellow]skipped[/yellow]")
        return
    cfgmod.set_env_var("DISCORD_BOT_TOKEN", token)
    owner = Prompt.ask("Your numeric Discord user id (optional -- restricts /admin commands)", default="")
    cfg["bots"]["discord"]["enabled"] = True
    cfg["bots"]["discord"]["owner_id"] = int(owner) if owner.strip().isdigit() else None
    prefix = Prompt.ask("Command prefix for Discord (mentioning the bot always works too)", default="!ai ")
    cfg["bots"]["discord"]["command_prefix"] = prefix
    console.print("[green]Discord bot configured.[/green] Start it with: ai bots run discord")


def needs_setup(cfg: Dict[str, Any]) -> bool:
    return not cfg.get("setup_complete", False)
