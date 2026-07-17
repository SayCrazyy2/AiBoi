"""
Configuration handling.

Config lives at ~/.ai-cli/config.yaml by default. API keys are read from
environment variables first (ANTHROPIC_API_KEY, OPENAI_API_KEY, ...) and
fall back to values in the config file. MCP servers are declared in
~/.ai-cli/mcp_servers.json (or a path you point to with --mcp-config).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

APP_DIR = Path(os.environ.get("AI_CLI_HOME", Path.home() / ".ai-cli"))
CONFIG_PATH = APP_DIR / "config.yaml"
MCP_SERVERS_PATH = APP_DIR / "mcp_servers.json"
SESSIONS_DIR = APP_DIR / "sessions"

DEFAULT_CONFIG: Dict[str, Any] = {
    "default_model": "claude-sonnet-5",
    "default_system_prompt": (
        "You are a helpful, precise assistant running in a terminal. "
        "Use tools when they let you give a more accurate or up to date answer. "
        "Keep responses concise unless the user asks for depth."
    ),
    "models": {
        # Friendly name -> provider config. `model` is the string sent to the API.
        "claude-sonnet-5": {"provider": "anthropic", "model": "claude-sonnet-5"},
        "claude-opus-4-8": {"provider": "anthropic", "model": "claude-opus-4-8"},
        "claude-haiku-4-5": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        "gpt-4o": {"provider": "openai", "model": "gpt-4o"},
        "gpt-4o-mini": {"provider": "openai", "model": "gpt-4o-mini"},
        "local-llama3": {"provider": "ollama", "model": "llama3"},
        # -- Free-tier options (no paid key needed) --
        # All three reuse the "openai" provider by pointing base_url at a
        # different OpenAI-compatible endpoint. Get a free key, export the
        # env var below, and pick one of these with `-m` or `/model`.
        "groq-llama": {
            "provider": "openai",
            "model": "llama-3.3-70b-versatile",
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY",
        },
        "openrouter-free": {
            "provider": "openai",
            "model": "meta-llama/llama-3.3-70b-instruct:free",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY",
        },
        "gemini-flash": {
            "provider": "openai",
            "model": "gemini-2.5-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "api_key_env": "GEMINI_API_KEY",
        },
    },
    "provider_options": {
        "anthropic": {"api_key_env": "ANTHROPIC_API_KEY", "max_tokens": 4096},
        "openai": {"api_key_env": "OPENAI_API_KEY", "max_tokens": 4096},
        "ollama": {"base_url": "http://localhost:11434"},
        # Defaults for the dedicated third-party provider keys (used when a
        # model sets provider: openrouter / groq / together / deepseek
        # directly instead of overriding base_url on an "openai" model).
        "openrouter": {"api_key_env": "OPENROUTER_API_KEY", "base_url": "https://openrouter.ai/api/v1", "max_tokens": 4096},
        "groq": {"api_key_env": "GROQ_API_KEY", "base_url": "https://api.groq.com/openai/v1", "max_tokens": 4096},
        "together": {"api_key_env": "TOGETHER_API_KEY", "base_url": "https://api.together.xyz/v1", "max_tokens": 4096},
        "deepseek": {"api_key_env": "DEEPSEEK_API_KEY", "base_url": "https://api.deepseek.com", "max_tokens": 4096},
        "openai_compatible": {"api_key_env": "OPENAI_COMPATIBLE_API_KEY", "base_url": "", "max_tokens": 4096},
    },
    "tools": {
        "enable_shell": False,          # shell exec is off by default -- opt in
        "enable_filesystem": True,
        "enable_http": True,
        "confirm_before_write": True,
        "confirm_before_shell": True,
    },
    "ui": {
        "stream": True,
        "markdown": True,
        "show_token_usage": True,
    },
    "bots": {
        "telegram": {
            "enabled": False,
            "token_env": "TELEGRAM_BOT_TOKEN",
            "owner_id": None,        # your numeric Telegram user id; null = anyone can use it
            "allowed_chat_ids": [],  # empty = allow any chat
            "model": None,           # null = use default_model
        },
        "discord": {
            "enabled": False,
            "token_env": "DISCORD_BOT_TOKEN",
            "owner_id": None,            # your numeric Discord user id
            "allowed_guild_ids": [],     # empty = allow any server
            "command_prefix": "!ai ",
            "respond_to_mentions": True,
            "model": None,
        },
    },
    "setup_complete": False,
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    ensure_app_dir()
    cfg_path = path or CONFIG_PATH
    if cfg_path.exists():
        with open(cfg_path, "r") as f:
            user_cfg = yaml.safe_load(f) or {}
        return _deep_merge(DEFAULT_CONFIG, user_cfg)
    return dict(DEFAULT_CONFIG)


def save_config(cfg: Dict[str, Any], path: Optional[Path] = None) -> None:
    ensure_app_dir()
    cfg_path = path or CONFIG_PATH
    with open(cfg_path, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)


def write_default_config_if_missing() -> None:
    ensure_app_dir()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
    if not MCP_SERVERS_PATH.exists():
        with open(MCP_SERVERS_PATH, "w") as f:
            json.dump({"mcpServers": {}}, f, indent=2)


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)


def load_mcp_servers(path: Optional[Path] = None) -> List[MCPServerConfig]:
    servers_path = path or MCP_SERVERS_PATH
    if not servers_path.exists():
        return []
    with open(servers_path, "r") as f:
        data = json.load(f)
    servers = []
    for name, spec in (data.get("mcpServers") or {}).items():
        servers.append(
            MCPServerConfig(
                name=name,
                command=spec["command"],
                args=spec.get("args", []),
                env=spec.get("env", {}),
            )
        )
    return servers


def resolve_api_key(env_var: str) -> Optional[str]:
    return os.environ.get(env_var)


ENV_FILE_PATH = APP_DIR / ".env"


def load_env_file(path: Optional[Path] = None) -> None:
    """
    Loads KEY=VALUE lines from ~/.ai-cli/.env into os.environ, without
    overwriting anything already set in the real environment. Call this
    once at startup before load_config() / build_provider().
    """
    env_path = path or ENV_FILE_PATH
    if not env_path.exists():
        return
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def set_env_var(key: str, value: str, path: Optional[Path] = None) -> None:
    """Persists a KEY=VALUE pair to ~/.ai-cli/.env (creating/updating it) and sets it in os.environ now."""
    ensure_app_dir()
    env_path = path or ENV_FILE_PATH
    existing: Dict[str, str] = {}
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()
    existing[key] = value
    with open(env_path, "w") as f:
        f.write("# API keys and bot tokens -- keep this file private.\n")
        for k, v in existing.items():
            f.write(f"{k}={v}\n")
    try:
        env_path.chmod(0o600)
    except OSError:
        pass
    os.environ[key] = value


# -- deployment / non-interactive support ------------------------------------
#
# Railway, a VPS running under systemd, a Docker container, or CI all have
# one thing in common: nobody is sitting at a keyboard to answer wizard
# prompts. In those environments the whole config is expected to come from
# environment variables (set in the Railway dashboard, a systemd
# EnvironmentFile, `docker run -e ...`, etc.) instead of an interactive
# session writing ~/.ai-cli/config.yaml.

_TRUE_STRINGS = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in _TRUE_STRINGS


def _env_int_list(name: str) -> List[int]:
    raw = os.environ.get(name, "")
    out = []
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


def is_running_in_container() -> bool:
    return Path("/.dockerenv").exists() or os.environ.get("container") is not None


def is_running_on_railway() -> bool:
    return bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID"))


def is_noninteractive() -> bool:
    """
    True when nobody can answer wizard prompts: explicitly forced via
    AI_CLI_NONINTERACTIVE, running on Railway, inside a container, or
    stdin isn't a real terminal (piped input, a supervisor like systemd, CI).
    """
    if os.environ.get("AI_CLI_NONINTERACTIVE") is not None:
        return _env_bool("AI_CLI_NONINTERACTIVE", True)
    if is_running_on_railway() or is_running_in_container():
        return True
    try:
        import sys

        if not sys.stdin.isatty():
            return True
    except Exception:  # noqa: BLE001
        return True
    return False


def config_from_env(base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Builds a full config purely from environment variables -- no file on
    disk required. Used automatically on first run in a non-interactive
    environment (Railway, Docker, systemd, CI) so a deploy only needs env
    vars set, never a terminal session.
    """
    cfg = _deep_merge(DEFAULT_CONFIG, base or {})

    if os.environ.get("AI_DEFAULT_MODEL"):
        cfg["default_model"] = os.environ["AI_DEFAULT_MODEL"]
    if os.environ.get("AI_SYSTEM_PROMPT"):
        cfg["default_system_prompt"] = os.environ["AI_SYSTEM_PROMPT"]

    cfg["tools"]["enable_filesystem"] = _env_bool("AI_ENABLE_FILESYSTEM", cfg["tools"]["enable_filesystem"])
    cfg["tools"]["enable_http"] = _env_bool("AI_ENABLE_HTTP", cfg["tools"]["enable_http"])
    cfg["tools"]["enable_shell"] = _env_bool("AI_ENABLE_SHELL", cfg["tools"]["enable_shell"])

    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        tg = cfg["bots"]["telegram"]
        tg["enabled"] = True
        if os.environ.get("TELEGRAM_OWNER_ID", "").strip().lstrip("-").isdigit():
            tg["owner_id"] = int(os.environ["TELEGRAM_OWNER_ID"])
        if os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS"):
            tg["allowed_chat_ids"] = _env_int_list("TELEGRAM_ALLOWED_CHAT_IDS")
        if os.environ.get("TELEGRAM_MODEL"):
            tg["model"] = os.environ["TELEGRAM_MODEL"]

    if os.environ.get("DISCORD_BOT_TOKEN"):
        dc = cfg["bots"]["discord"]
        dc["enabled"] = True
        if os.environ.get("DISCORD_OWNER_ID", "").strip().lstrip("-").isdigit():
            dc["owner_id"] = int(os.environ["DISCORD_OWNER_ID"])
        if os.environ.get("DISCORD_ALLOWED_GUILD_IDS"):
            dc["allowed_guild_ids"] = _env_int_list("DISCORD_ALLOWED_GUILD_IDS")
        if os.environ.get("DISCORD_COMMAND_PREFIX"):
            dc["command_prefix"] = os.environ["DISCORD_COMMAND_PREFIX"]
        if os.environ.get("DISCORD_MODEL"):
            dc["model"] = os.environ["DISCORD_MODEL"]

    cfg["setup_complete"] = True
    return cfg


def load_config_auto(path: Optional[Path] = None) -> Dict[str, Any]:
    """
    load_config() if a config file exists; otherwise, in a non-interactive
    environment, build one straight from environment variables so a fresh
    Railway/Docker/systemd deploy works without ever touching a wizard.
    """
    cfg_path = path or CONFIG_PATH
    if cfg_path.exists():
        return load_config(path)
    if is_noninteractive():
        return config_from_env()
    return load_config(path)
