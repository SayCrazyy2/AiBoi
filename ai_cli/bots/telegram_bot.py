"""
Telegram bot frontend with Telethon + MTProto for true streaming using Rich Drafts.

Implements:
- Private chats: Animated Rich Drafts with thinking states, streaming markdown updates
- Group chats: Placeholder message + live editing (Rich Drafts don't work in groups)
- Support for Rich Markdown formatting throughout streaming

Authentication: uses TELEGRAM_BOT_TOKEN (bot account) with Telethon's MTProto,
NOT the HTTP Bot API. Still needs TELEGRAM_API_ID and TELEGRAM_API_HASH from
https://my.telegram.org for MTProto.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from typing import Any, Callable, Dict, List, Optional

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.functions import messages
from telethon.tl import types

from .. import config as cfgmod
from .common import BotEngine

logger = logging.getLogger(__name__)

MAX_MESSAGE_LEN = 4000
STREAM_UPDATE_INTERVAL = 0.45

# Telegram's random_id must fit in a signed 64-bit integer
_INT64_MAX = 2**63 - 1

# ---------------------------------------------------------------------------
# Predefined allowlist of shell commands the Telegram bot can run without
# asking for confirmation.  Only the first token of the command is checked,
# so "ls -la /tmp" is allowed but "rm -rf /" is not.
#
# Set TELEGRAM_SHELL_ALLOWLIST to a comma-separated list to override at
# deploy time, or set it to "*" to allow everything.
# ---------------------------------------------------------------------------
_DEFAULT_SHELL_ALLOWLIST: List[str] = [
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "echo",
    "grep",
    "find",
    "wc",
    "sort",
    "uniq",
    "date",
    "whoami",
    "uname",
    "df",
    "du",
    "free",
    "uptime",
    "env",
    "git",
    "python3",
    "python",
    "pip",
    "pip3",
    "node",
    "npm",
    "curl",
    "wget",
    "docker",
    "systemctl",
    "ps",
    "top",
    "htop",
    "kill",
    "mkdir",
    "touch",
    "cp",
    "mv",
    "sed",
    "awk",
    "tr",
    "cut",
    "tee",
    "which",
    "whereis",
    "file",
    "stat",
    "diff",
    "tree",
    "history",
    "hostname",
    "ip",
    "ifconfig",
    "netstat",
    "ss",
    "ping",
    "nslookup",
    "dig",
]


def _resolve_allowlist() -> Optional[List[str]]:
    """
    Resolve the shell-command allowlist from the environment.

    Priority:
      1. TELEGRAM_SHELL_ALLOWLIST="*"           -> None  (everything allowed)
      2. TELEGRAM_SHELL_ALLOWLIST="ls,git,cat"  -> ["ls","git","cat"]
      3. (unset)                                -> _DEFAULT_SHELL_ALLOWLIST
    """
    raw = os.environ.get("TELEGRAM_SHELL_ALLOWLIST")
    if raw is not None:
        raw = raw.strip()
        if raw == "*":
            return None  # None = no restriction
        return [c.strip() for c in raw.split(",") if c.strip()] or _DEFAULT_SHELL_ALLOWLIST
    return _DEFAULT_SHELL_ALLOWLIST


class TelegramConfigError(RuntimeError):
    pass


def _validate_telegram_config(bot_cfg: Dict[str, Any]) -> tuple:
    """
    Validate Telegram credentials for MTProto bot authentication.
    Returns (api_id_int, api_hash, bot_token) on success.
    """
    api_id = cfgmod.resolve_api_key(bot_cfg.get("api_id_env", "TELEGRAM_API_ID"))
    api_hash = cfgmod.resolve_api_key(bot_cfg.get("api_hash_env", "TELEGRAM_API_HASH"))
    bot_token = cfgmod.resolve_api_key(bot_cfg.get("token_env", "TELEGRAM_BOT_TOKEN"))

    missing: List[str] = []
    if not api_id:
        missing.append("TELEGRAM_API_ID")
    if not api_hash:
        missing.append("TELEGRAM_API_HASH")
    if not bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")

    if missing:
        env_file = cfgmod.ENV_FILE_PATH
        raise TelegramConfigError(
            "Telegram bot is missing required credentials: "
            + ", ".join(missing)
            + "\n\nThis bot uses Telethon (MTProto) with a bot token. You need:\n"
            "  TELEGRAM_API_ID     — from https://my.telegram.org → API development tools\n"
            "  TELEGRAM_API_HASH   — same place\n"
            "  TELEGRAM_BOT_TOKEN  — from @BotFather\n\n"
            "Add them to your env file ("
            + str(env_file)
            + "):\n\n"
            "     TELEGRAM_API_ID=123456\n"
            "     TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890\n"
            "     TELEGRAM_BOT_TOKEN=123456789:ABCdef...\n\n"
            "  Or set them as environment variables and retry."
        )

    try:
        api_id_int = int(api_id)
    except (TypeError, ValueError):
        raise TelegramConfigError(
            f"TELEGRAM_API_ID must be a numeric integer, got: {api_id!r}"
        )

    return api_id_int, api_hash, bot_token


def _random_id() -> int:
    """Generate a random_id that fits in Telegram's signed int64."""
    return random.randint(0, _INT64_MAX)


class RichDraftManager:
    """Manages Rich Draft state for private chat streaming."""

    _icons = ["🔍", "🧠", "✍️", "💭", "⚡"]

    def __init__(self, client: TelegramClient):
        self.client = client
        self.draft_id: Optional[int] = None
        self._update_interval = STREAM_UPDATE_INTERVAL

    def _create_thinking_html(self, emoji: str, text: str) -> str:
        """Create HTML thinking animation."""
        return f"<tg-thinking>\n<tg-emoji emoji-id=\"5573473356579078196\">{emoji}</tg-emoji>\n{text}</tg-thinking>"

    async def _cycle_thinking(self, peer) -> None:
        """Cycle through thinking states before real content arrives."""
        thinking_htmls = [
            self._create_thinking_html(self._icons[0], "Searching..."),
            self._create_thinking_html(self._icons[1], "Analyzing..."),
            self._create_thinking_html(self._icons[2], "Writing..."),
        ]

        for thinking_html in thinking_htmls:
            try:
                await self.client(
                    messages.SetTypingRequest(
                        peer=peer,
                        action=types.InputSendMessageRichMessageDraftAction(
                            random_id=_random_id(),
                            rich_message=types.InputRichMessageHTML(html=thinking_html),
                        ),
                    )
                )
            except Exception:
                pass
            await asyncio.sleep(0.8)

    async def start_draft(self, peer) -> Optional[int]:
        """Start a Rich Draft for private chat."""
        try:
            self.draft_id = _random_id()
            await self._cycle_thinking(peer)
            return self.draft_id
        except Exception as e:
            logger.debug(f"Failed to start draft: {e}")
            return None

    async def update_draft(self, peer, text: str) -> None:
        """Update the Rich Draft with new text (throttled)."""
        if self.draft_id is None:
            return
        try:
            await self.client(
                messages.SetTypingRequest(
                    peer=peer,
                    action=types.InputSendMessageRichMessageDraftAction(
                        random_id=_random_id(),
                        rich_message=types.InputRichMessageMarkdown(
                            markdown=text[:1000]
                        ),
                    )
                )
            )
        except Exception:
            pass

    async def finish_draft(self, peer, text: str) -> bool:
        """Send the final message, which clears the draft."""
        if self.draft_id is None:
            return False
        try:
            await self.client(
                messages.SendMessageRequest(
                    peer=peer,
                    random_id=_random_id(),
                    message=text[:4000],
                    rich_message=types.InputRichMessageMarkdown(markdown=text),
                )
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send final message: {e}")
            return False


class TelegramBot:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg
        self.bot_cfg = cfg["bots"]["telegram"]

        api_id_int, api_hash, bot_token = _validate_telegram_config(self.bot_cfg)

        # --- shell tool configuration ------------------------------------
        # Shell is enabled with auto-confirm and a predefined allowlist.
        # The allowlist can be customised via TELEGRAM_SHELL_ALLOWLIST.
        allowlist = _resolve_allowlist()

        self.engine = BotEngine(
            cfg,
            "telegram",
            connect_mcp=False,
            enable_shell=True,
            auto_confirm=True,
            allowed_shell_commands=allowlist,
        )

        self._api_id_int = api_id_int
        self._api_hash = api_hash
        self._bot_token = bot_token
        self._client: Optional[TelegramClient] = None

    def run(self) -> None:
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        try:
            self._client = TelegramClient(
                StringSession(),
                self._api_id_int,
                self._api_hash,
            )
            await self._client.connect()

            if not self._client.is_connected():
                raise RuntimeError("Failed to connect to Telegram")

            await self._client.sign_in(bot_token=self._bot_token)

            me = await self._client.get_me()
            logger.info(
                "Telegram bot running as @%s (id=%s)",
                getattr(me, "username", "?"),
                me.id,
            )

            self._client.add_event_handler(
                self._handle_event, events.NewMessage(incoming=True)
            )

            await self._client.run_until_disconnected()
        except KeyboardInterrupt:
            logger.info("[telethon] stopped.")
        except Exception as e:
            logger.error(f"Bot error: {e}")
            raise
        finally:
            self.engine.close()
            if self._client and self._client.is_connected():
                await self._client.disconnect()

    # -- event handler ------------------------------------------------------

    async def _handle_event(self, event) -> None:
        if not hasattr(event, "message") or event.message is None:
            return

        message = event.message
        chat_id = str(message.chat.id)
        user_id = str(message.sender_id)
        text = message.text or ""

        logger.debug("Message from %s: %s", chat_id, text[:80])

        reply = self.engine.handle_command(chat_id, user_id, text)
        if reply is None:
            await self._handle_message(event, chat_id, text)
        elif reply:
            await self._send_message(event.chat, reply)

    async def _handle_message(self, event, chat_id: str, text: str) -> None:
        is_private = chat_id.isdigit() and int(chat_id) > 0
        if is_private:
            await self._handle_private_chat(event, text)
        else:
            await self._handle_group_chat(event, text)

    async def _handle_private_chat(self, event, text: str) -> None:
        """Handle private chat with Rich Draft streaming."""
        peer = event.chat
        loop = asyncio.get_running_loop()

        draft_mgr = RichDraftManager(self._client)
        await draft_mgr.start_draft(peer)

        current_text = ""
        last_update = 0.0

        def on_text(chunk: str) -> None:
            nonlocal current_text, last_update
            current_text += chunk
            now = time.time()
            if now - last_update >= STREAM_UPDATE_INTERVAL:
                last_update = now
                # We're in a worker thread — schedule the coroutine on the
                # main event loop, not asyncio.ensure_future (which needs a
                # loop in the current thread).
                asyncio.run_coroutine_threadsafe(
                    draft_mgr.update_draft(peer, current_text), loop
                )

        final_text = await asyncio.to_thread(
            self.engine.reply_with_log,
            str(event.chat_id),
            text,
            True,
            on_text,
        )

        success = await draft_mgr.finish_draft(peer, final_text)
        if not success:
            await self._send_message(peer, final_text)

    async def _handle_group_chat(self, event, text: str) -> None:
        """Handle group chat with message editing (no Rich Drafts)."""
        peer = event.chat
        loop = asyncio.get_running_loop()

        msg = await self._client.send_message(peer, "🤔…")
        current_text = ""
        last_update = 0.0

        def on_text(chunk: str) -> None:
            nonlocal current_text, last_update
            current_text += chunk
            now = time.time()
            if now - last_update >= STREAM_UPDATE_INTERVAL:
                last_update = now
                asyncio.run_coroutine_threadsafe(
                    self._edit_message(msg, current_text + "▌"), loop
                )

        final_text = await asyncio.to_thread(
            self.engine.reply_with_log,
            str(event.chat_id),
            text,
            True,
            on_text,
        )

        await self._edit_message(msg, final_text)

    # -- Message sending helpers --------------------------------------------

    async def _send_message(self, peer, text: str) -> None:
        text = text or "(empty response)"
        try:
            await self._client.send_message(peer, text[:MAX_MESSAGE_LEN])
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    async def _edit_message(self, msg, text: str) -> None:
        text = text or "(empty response)"
        if len(text) > MAX_MESSAGE_LEN:
            text = text[:MAX_MESSAGE_LEN]
        try:
            await msg.edit(text)
        except Exception as e:
            logger.debug(f"Failed to edit message: {e}")


if __name__ == "__main__":
    from ai_cli import config as cfgmod
    cfg = cfgmod.APP_CONFIG
    bot = TelegramBot(cfg)
    bot.run()
