# Codebase Summary — ai-cli-assistant

## Overview

Terminal AI assistant: multi-model (Anthropic, OpenAI, Ollama, OpenAI-compatible), MCP tool integration, built-in tools, sessions, streaming REPL, one-shot mode, Telegram/Discord bots. Deploys on Railway/Docker/VPS/macOS.

**Version:** 0.1.0  **Python:** >=3.9  **Entry:** `ai` console script or `python main.py`

---

## Top-Level Files

#### main.py (207 bytes)
Entry-point shim. Imports `ai_cli.cli.main`, calls with `sys.exit()` under `__main__`. Enables `python main.py "prompt"` (one-shot) or `python main.py` (REPL).

#### pyproject.toml (522 bytes)
PEP 621 setuptools config. Deps: rich>=13.0, pyyaml>=6.0, requests>=2.31, anthropic>=0.40, openai>=1.40. Console script `ai = ai_cli.cli:main`. Packages: ai_cli + providers/mcp/tools/bots.

#### requirements.txt (101 bytes)
rich, pyyaml, requests, anthropic, openai, discord.py>=2.3,<3, telethon>=1.36.

#### requirements-bots.txt (191 bytes)
Legacy (empty). Discord moved to requirements.txt.

#### Dockerfile (963 bytes)
python:3.12-slim. Installs git/curl/ca-certs. pip install + -e . Env AI_CLI_HOME=/data/.ai-cli, AI_CLI_NONINTERACTIVE=1. EXPOSE 8080. CMD `["ai", "serve"]`.

#### Procfile (17 bytes)
`worker: ai serve`.

#### railway.json (352 bytes)
Builder DOCKERFILE. startCommand `ai serve`, healthcheckPath `/health` (timeout 300), restart ON_FAILURE max 10, 1 replica.

#### README.md (15690 bytes)
Full docs: features, deploy, install, usage, REPL commands, MCP catalog, bots, providers, tool safety, layout.

#### config.example.yaml (3544 bytes)
Annotated config: default_model, system_prompt, models, provider_options, tools (enable flags + confirm), ui, bots (telegram/discord), setup_complete.

#### mcp_servers.json / mcp_servers.example.json (1940 bytes each, identical)
16 MCP servers: filesystem, fetch, git, memory, sequential-thinking, time, puppeteer, everything, sqlite, postgres, github, brave-search, google-drive, slack, google-maps, everart.

#### setup.sh (10440 bytes)
Installer. Flags --yes/--no-venv/--no-service/--no-wizard. Detects platform, installs Python 3.9+, venv, deps, wizard, systemd/launchd service.

#### setup_mcp.sh (2347 bytes)
Installs Node.js LTS + uv/uvx, pre-caches 12 npx + 4 uvx MCP packages.

#### prompt.txt (6490 bytes)
Spec for Telethon MTProto Rich Draft streaming: draft_id, SetTypingRequest, InputSendMessageRichMessageDraftAction, InputRichMessageHTML/Markdown, thinking cycle ~0.8s, streaming throttled 300-500ms, final SendMessageRequest, group EditMessageRequest fallback, Rich Markdown, tool footer.

#### stream_eaxmple.py (5156 bytes)
Standalone Telethon Rich Draft demo (filename typo). `/start` returns rich demo message. Rich Drafts (private) + thinking cycling, EditMessageRequest (groups). Incremental block reveal (STREAM_DELAY=0.5s).

#### telegram_bot.py (10802 bytes, top-level)
Standalone Telethon demo bot with file/media handling. Commands /start /restart /upload /send. Rich Draft streaming (private) + editing (groups). API_ID/API_HASH/BOT_TOKEN are empty placeholders.

---

## Package: ai_cli/

### ai_cli/__init__.py (22 bytes)
`__version__ = "0.1.0"`.

### ai_cli/cli.py (13743 bytes) — main entrypoint & command router
`build_arg_parser()`: args prompt, -m/--model, --system, --config, --mcp-config, --no-mcp, --no-stream, --no-tools, --list-models, --init, --setup, --load.
`main()`: loads .env, routes `bots`/`setup`/`serve`/`mcp` sub-CLIs before argparse. On first run: wizard (interactive) or `config_from_env()` (noninteractive). Handles --init, --list-models, --setup.
`_run_one_shot()`: builds MCPManager + ToolRegistry, connects MCP, builds provider, runs one `Session.run_turn`, streams to console, renders markdown if non-stream.
`_handle_bots()`: `ai bots setup|run|status [telegram|discord|all]`. Delegates to wizard._setup_*; runs bots via threads for `all`.
`_run_telegram/_run_discord/_run_all`: start bots; `all` runs Telegram in a daemon thread + Discord in main thread.
`_cmd_serve()`: production entrypoint. Loads config (file or env), starts health server on $PORT, runs configured bots; stays up (no crash-loop) if none configured.
`_cli_confirm()`: y/N prompt for write/shell confirmation.

### ai_cli/config.py (12835 bytes) — config loading & env-from-config
Paths: APP_DIR=~/.ai-cli, CONFIG_PATH, MCP_SERVERS_PATH, SESSIONS_DIR, ENV_FILE_PATH. Honors AI_CLI_HOME.
`DEFAULT_CONFIG`: default_model claude-sonnet-5, system_prompt, 9 models, provider_options (8 providers), tools (shell off), ui, bots, setup_complete=False.
`_deep_merge()`, `ensure_app_dir()`, `load_config()` (deep-merge), `save_config()`, `write_default_config_if_missing()`.
`MCPServerConfig` dataclass. `load_mcp_servers()`. `resolve_api_key()`.
`load_env_file()` (loads ~/.ai-cli/.env without overwriting). `set_env_var()` (persists, chmod 600).
Deployment: `_env_bool`, `_env_int_list`, `is_running_in_container()`, `is_running_on_railway()`, `is_noninteractive()`, `config_from_env()`, `load_config_auto()`.

### ai_cli/health.py (1594 bytes) — health-check HTTP server
`_Handler`: GET /, /health, /healthz -> 200 "ok"; else 404. Suppresses logs.
`start_health_server(port, status_fn)`: ThreadingHTTPServer on 0.0.0.0:port in daemon thread.

### ai_cli/mcp_tool.py (16257 bytes) — `ai mcp` subcommand & catalog
`MCPCatalogEntry` dataclass. `CATALOG`: 16 servers (10 no-key, 6 with-key).
Commands: `cmd_list`, `cmd_installed`, `cmd_add` (interactive path+env, overwrite confirm, pre-download), `cmd_remove`, `cmd_install` (pre-cache), `cmd_add_custom`.
`handle_mcp(console, sub_argv)`: dispatch.

### ai_cli/repl.py (9380 bytes) — interactive REPL & slash commands
`REPL.__init__`: Console, cfg, model_name, stream, MCPManager, ToolRegistry (confirm_fn), connects MCP, new session.
`run()`: welcome panel, input loop (`you> `), routes `/` commands vs messages.
Slash commands: /help /model /models /system /tools /mcp /save /load /sessions /usage /clear /stream /exit /quit.
`_switch_model()`: preserves history. `_handle_message()`: streams live or renders Markdown at once.

### ai_cli/session.py (5101 bytes) — conversation state & tool loop
`MAX_TOOL_ITERATIONS = 10`. `SessionStats`, `Session`.
`run_turn()`: append user text, loop _complete -> add usage -> append assistant -> if tool_uses & stop_reason==tool_use: execute tools (timing), append results, continue; else return.
`_complete()`: stream (text_delta) or non-stream. Persistence: `to_dict`, `save`, `list_saved`, `load_messages`.

### ai_cli/wizard.py (6436 bytes) — first-run setup wizard
`PROVIDER_KEY_INFO`/`PROVIDER_LABELS`. `run_setup_wizard()`: Step1 provider+key+model, Step2 tool perms, Step3 bots. `_setup_telegram()`, `_setup_discord()`, `needs_setup()`.

### ai_cli/providers/__init__.py (2303 bytes) — provider registry
`_lazy_registry()`: anthropic->Anthropic, openai->OpenAI, ollama->Ollama, openrouter/groq/together/deepseek/openai_compatible->OpenAI.
`build_provider()`: merges provider_options + per-model overrides, resolves api_key.

### ai_cli/providers/base.py (2710 bytes) — Provider ABC & normalized types
Normalized msg `{role, content:[Block]}`. Blocks: text, tool_use, tool_result.
`ToolSpec`, `Usage`, `StreamEvent` (text_delta/tool_use_start/tool_use_delta/message_stop), `CompletionResult`. `Provider(ABC)`: abstract complete, stream default fallback. `ProviderError`.

### ai_cli/providers/anthropic_provider.py (5370 bytes)
`AnthropicProvider`. Converts normalized<->Anthropic blocks. complete() via messages.create; stream() via messages.stream (content_block_start/delta, message_stop).

### ai_cli/providers/openai_provider.py (7297 bytes)
`OpenAIProvider` (also OpenRouter/Groq/Together/DeepSeek/Gemini/custom via base_url). Converts normalized<->OpenAI (tool_calls, role:tool messages). complete() + stream() (accumulate text + tool_calls by index).

### ai_cli/providers/ollama_provider.py (5755 bytes)
`OllamaProvider`. HTTP /api/chat. complete() (stream=False) + stream() (iter_lines). usage from prompt_eval_count/eval_count.

### ai_cli/mcp/__init__.py (0 bytes) — empty
### ai_cli/mcp/client.py (6091 bytes) — stdio JSON-RPC client
`MCPClient`: spawns child process, reader/stderr threads, Queue. `start` (initialize + tools/list), `stop`. `_request`/`_notify`. `call_tool` (tools/call, joins text, raises on isError). PROTOCOL_VERSION 2024-11-05. Dependency-free.

### ai_cli/mcp/manager.py (2498 bytes) — multi-server manager
`namespaced_tool_name` -> `mcp__server__tool`. `MCPManager`: connect_all, disconnect_all, tool_specs, is_mcp_tool, _split, call.

### ai_cli/tools/__init__.py (0 bytes) — empty
### ai_cli/tools/builtin.py (8535 bytes) — built-in tools
`make_builtin_tools()`: read_file (50k cap), write_file (confirm), list_directory (500 cap), run_shell_command (confirm, 30s), http_get (20k cap), calculator (AST safe eval). `ToolExecutionError`.

### ai_cli/tools/registry.py (1912 bytes) — tool merge layer
`ToolRegistry`: register_builtin, all_specs (local + MCP), call (local or mcp_manager).

### ai_cli/bots/__init__.py (55 bytes)
`from .common import BotEngine`.

### ai_cli/bots/common.py (11234 bytes) — shared bot engine & tool-call log
`ToolCallRecord`, `TurnLog.format_log()` (Rich Markdown footer: 🔧 calls, per-call ✅/❌ + args + result block, 📦 MCP breakdown). `BotEngine`: session_for, is_owner, handle_command (/start /help /reset /model /system /tools /usage /whoami), reply_with_log (stream + on_text, tool timing, footer), close.

### ai_cli/bots/telegram_bot.py (11810 bytes) — Telethon MTProto frontend
`TelegramConfigError`. `_validate_telegram_config` (API_ID/HASH/TOKEN). `RichDraftManager`: thinking cycle (3 HTML states, 0.8s), update_draft (Markdown, 1000 cap), finish_draft (SendMessageRequest). `TelegramBot.run` -> asyncio: StringSession, sign_in(bot_token), NewMessage handler. Private: Rich Draft streaming (throttled 0.45s via run_coroutine_threadsafe). Group: edit message (▌ cursor). 4000 cap.

### ai_cli/bots/discord_bot.py (3351 bytes) — discord.py gateway frontend
`run_discord_bot`: resolves DISCORD_BOT_TOKEN, intents(message_content), BotEngine("discord"). on_message: skip bots, guild allowlist, prefix/DM/mention parse, typing, asyncio.to_thread(engine.reply), chunk to 1900 chars. client.run + engine.close.

---

## Build Metadata: ai_cli_assistant.egg-info/

- **PKG-INFO** (305 bytes): Metadata 2.4, name, version, summary, Requires-Python, 5 Requires-Dist.
- **SOURCES.txt** (789 bytes): all 30 tracked files.
- **top_level.txt** (7 bytes): `ai_cli`.
- **requires.txt** (67 bytes): 5 runtime deps.
- **entry_points.txt** (39 bytes): `[console_scripts] ai = ai_cli.cli:main`.
- **dependency_links.txt** (1 byte): empty.

---

## Summary Statistics

- **Python source files:** 24 (in ai_cli/ + 2 standalone top-level)
- **Config/infra files:** 11
- **Entry points:** `ai` console script, `python main.py`
- **Providers:** 3 classes (Anthropic, OpenAI [reused 6+ endpoints], Ollama)
- **Built-in tools:** 6 (read_file, write_file, list_directory, run_shell_command, http_get, calculator)
- **MCP catalog:** 16 servers
- **Bots:** Telegram (Telethon MTProto + Rich Drafts) + Discord (discord.py)
- **Key limits:** MAX_TOOL_ITERATIONS=10, msg caps 4000 TG / 1900 Discord, stream throttle 0.45s, read 50k chars, http 20k chars, shell 30s
