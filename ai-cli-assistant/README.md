# ai-cli-assistant

A terminal AI assistant with:

- **Multi-model support** — Anthropic (Claude), OpenAI (GPT), local models via Ollama, and third-party OpenAI-compatible providers (OpenRouter, Groq, Together, DeepSeek, Gemini's OpenAI endpoint, or any custom one) behind a single provider interface. Switch models mid-conversation with `/model <name>`.
- **MCP support** — connects to any [Model Context Protocol](https://modelcontextprotocol.io) server (filesystem, GitHub, fetch, your own, ...) over stdio and exposes their tools to the model automatically.
- **Tool calling** — one normalized tool-calling loop that works the same way across every provider, with built-in tools (file read/write, list directory, HTTP GET, calculator, optional shell exec) plus anything your MCP servers add.
- **Bots** — host the assistant as a Telegram and/or Discord bot, so it's one tap away on your phone. Same tool-calling engine, same models, its own per-chat conversation memory and slash commands.
- **Setup wizard** — first time you run `ai` (or any time with `ai --setup`), a guided walkthrough picks a provider, stores keys safely, sets tool permissions, and optionally configures bots. No manual YAML editing required.
- **Sessions** — save/load conversations, switch models without losing history, per-session token usage stats.
- **Streaming REPL** — live token streaming, markdown rendering, confirmation prompts before writes/shell commands, slash commands.
- **One-shot mode** — `ai "summarize this file for me"` for scripting/piping, or a full REPL when run with no arguments.

## Install

```bash
cd ai-cli-assistant
pip install -r requirements.txt
# optional, to get the `ai` command on your PATH:
pip install -e .
# only if you want the Discord bot (Telegram needs nothing extra):
pip install -r requirements-bots.txt
```

## First run

Just run it — there's nothing to configure by hand:

```bash
ai
```

The first time it finds no config, it launches a setup wizard that:

1. Lists providers (Anthropic, OpenAI, OpenRouter, Groq, Together, DeepSeek, Ollama) and asks which one to use by default, prompting for that provider's API key if it isn't already in your environment. Keys are saved to `~/.ai-cli/.env` (created with `chmod 600`), never written into `config.yaml`.
2. Asks about tool permissions (filesystem, HTTP, shell — shell defaults to off).
3. Optionally walks through Telegram and/or Discord bot setup.

Re-run it any time with:

```bash
ai --setup
# or just:
ai setup
```

Non-interactive alternative (writes bare defaults, no prompts):

```bash
ai --init
```

## Usage

Interactive REPL:

```bash
ai
```

One-shot:

```bash
ai "what's the weather API at https://example.com returning right now?"
```

Pick a model / system prompt / config for a run:

```bash
ai -m groq-llama "fast free-tier answer"
ai -m openrouter-free --system "answer only in haiku" "describe recursion"
ai --list-models
ai --no-tools "just chat, no tool calls"
ai --no-mcp "skip connecting to MCP servers this run"
```

### REPL slash commands

```
/help                 show all commands
/model [name]         show or switch the active model (history is preserved)
/models               list configured models
/system <prompt>      change the system prompt for this session
/tools                list all available tools (built-in + MCP)
/mcp                  list connected MCP servers
/save [name]          save the current conversation to ~/.ai-cli/sessions
/load <name>          load a previously saved conversation
/sessions             list saved conversations
/usage                show token usage for this session
/clear                clear conversation history
/stream on|off        toggle streaming output
/exit, /quit          leave
```

## Bots

Run the assistant as a Telegram and/or Discord bot so it's reachable from
your phone without any local terminal at all.

```bash
ai bots setup              # walks through both platforms
ai bots setup telegram     # just Telegram
ai bots setup discord      # just Discord
ai bots status             # what's configured
ai bots run telegram       # start the Telegram bot (blocks, Ctrl+C to stop)
ai bots run discord        # start the Discord bot
ai bots run all            # start whichever ones are configured, together
```

**Telegram**: message [@BotFather](https://t.me/BotFather) with `/newbot`,
copy the token when asked during `ai bots setup telegram`. Uses long polling
over plain HTTPS — no extra dependency, no inbound port needed, works fine
from behind NAT/mobile data.

**Discord**: create an application + bot at
https://discord.com/developers/applications, enable **Message Content
Intent** under the Bot tab, copy the token when asked during
`ai bots setup discord`. Needs `pip install -r requirements-bots.txt`
(pulls in `discord.py`).

Both bots share the same command set:

```
/help                 what the bot can do
/reset                clear this chat's conversation history
/model [name]         show or switch model (switching is owner-only)
/system [prompt]      show or set this chat's system prompt (owner-only to set)
/tools                list available tools
/usage                token usage for this chat
/whoami               your user id and this chat's id (handy for allowlisting)
```

Anything that isn't a command is just sent to the assistant as a normal
message — the bot keeps a separate conversation per chat/channel/DM.

**Access control**: `owner_id` (set during setup) gates which user can
change the model or system prompt. `allowed_chat_ids` (Telegram) /
`allowed_guild_ids` (Discord) restrict which chats/servers the bot responds
in at all — leave empty to allow anywhere it's added. Use `/whoami` in a
chat to find the id to put in either list.

**Safety**: bots never run shell commands and never ask for write
confirmation over chat (there's no safe "are you sure?" prompt when the
"user" is a remote chat account) — file writes and shell exec stay REPL/CLI
only, gated by `confirm_before_write` / `confirm_before_shell` in config.

## Adding MCP servers

Edit `~/.ai-cli/mcp_servers.json`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/you/projects"]
    },
    "fetch": {
      "command": "uvx",
      "args": ["mcp-server-fetch"]
    }
  }
}
```

Any MCP server that speaks stdio JSON-RPC works — the client here doesn't
depend on the official MCP SDK, it implements the `initialize` /
`tools/list` / `tools/call` handshake directly. Tools from server `foo` show
up to the model namespaced as `mcp__foo__<tool_name>` so multiple servers
can't collide on tool names. Bots pick up the same MCP servers automatically.

## Adding a model or provider

Most third-party providers (OpenRouter, Groq, Together, DeepSeek, Gemini's
OpenAI-compatible endpoint, self-hosted vLLM/LM Studio/etc.) speak the same
wire format as OpenAI, so adding one is just a config entry — no new code:

```yaml
models:
  my-new-model:
    provider: openai_compatible   # or openai, openrouter, groq, ... — all the same client
    model: some-model-id
    base_url: https://api.example.com/v1
    api_key_env: EXAMPLE_API_KEY
```

To add a whole new *protocol* (e.g. Bedrock, Vertex's native API), implement
`Provider` in `ai_cli/providers/` (see `anthropic_provider.py` for the
shortest example) and register it in `ai_cli/providers/__init__.py`'s
`_lazy_registry()`.

## Tool safety

- `enable_shell` is **off by default** — turn it on in `config.yaml` (or say
  yes during the wizard) if you want the assistant to run shell commands.
- File writes and shell commands prompt for confirmation by default in the
  REPL/CLI (`confirm_before_write` / `confirm_before_shell`); bots never get
  shell access and never get to skip the write confirmation, so writes are
  simply unconfirmable there and blocked.

## Project layout

```
ai_cli/
  cli.py               argparse entrypoint, one-shot mode, `ai bots ...` routing
  repl.py               interactive REPL + slash commands
  wizard.py             first-run / `ai --setup` interactive setup wizard
  session.py             conversation state + agentic tool-calling loop
  config.py               config.yaml / mcp_servers.json / .env loading
  providers/
    base.py                Provider interface, normalized message/tool schema
    anthropic_provider.py
    openai_provider.py       also used for OpenRouter/Groq/Together/DeepSeek/custom (base_url override)
    ollama_provider.py
  mcp/
    client.py               stdio JSON-RPC client for a single MCP server
    manager.py               connects multiple servers, namespaces their tools
  tools/
    builtin.py                read_file, write_file, list_directory, run_shell_command, http_get, calculator
    registry.py                merges builtin + MCP tools into one toolbox
  bots/
    common.py                 BotEngine: shared per-chat sessions + slash commands for both platforms
    telegram_bot.py            long-polling Telegram frontend (plain HTTPS, no extra dependency)
    discord_bot.py             discord.py gateway frontend
```
