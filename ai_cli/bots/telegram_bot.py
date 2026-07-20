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
import base64
import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.functions import messages
from telethon.tl import types

from .. import config as cfgmod
from .common import BotEngine

logger = logging.getLogger(__name__)

MAX_MESSAGE_LEN = 4000
STREAM_UPDATE_INTERVAL = 0.30

# Directory for downloaded media from users
MEDIA_DIR = Path(os.environ.get("AI_CLI_HOME", Path.home() / ".ai-cli")) / "downloads"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Max image size to inline as base64 (5 MB)
_MAX_INLINE_IMAGE_SIZE = 5 * 1024 * 1024

# MIME types for text-based files we can read and include in the prompt
_TEXT_MIME_TYPES = {
    "text/plain", "text/markdown", "text/html", "text/css", "text/javascript",
    "application/json", "application/xml", "application/x-yaml",
    "text/x-python", "text/x-shellscript",
}

# File extensions for text-based files
_TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".html", ".css", ".js", ".mjs", ".json",
    ".xml", ".yaml", ".yml", ".py", ".sh", ".bash", ".rb", ".go", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".java", ".kt", ".swift", ".ts", ".tsx",
    ".jsx", ".vue", ".svelte", ".sql", ".toml", ".ini", ".cfg", ".conf",
    ".log", ".csv", ".tsv", ".env",
}

# Image MIME types we can send as vision content
_IMAGE_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
}

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

    _icons = ["🔍", "🧠", "✍️", "📝", "👣", "🤖", "🗣", "🛠", "⚡"]
    _icon_ids = ["5535365052359507996", "5537230721728380949", "5534951812081123354", "5537247356136718385", "5535039193190760468", "5537515087218081814", "5537354996607090745", "5537560399123054610", "5573333417954639880"]

    def _create_thinking_html(eid, emoji: str, text: str) -> str:
        """Create HTML thinking animation."""
        return f"<tg-thinking>\n<tg-emoji emoji-id=\"{eid}\">{emoji}</tg-emoji>\n{text}</tg-thinking>"

    # Built once at class-definition time so _cycle_thinking doesn't
    # rebuild the list on every call.
    _thinking_htmls = [
        _create_thinking_html(_icon_ids[0], _icons[0], "Searching..."),
        _create_thinking_html(_icon_ids[1], _icons[1], "Analyzing..."),
        _create_thinking_html(_icon_ids[2], _icons[2], "Writing..."),
        _create_thinking_html(_icon_ids[3], _icons[3], "Coding..."),
        _create_thinking_html(_icon_ids[4], _icons[4], "Walking..."),
        _create_thinking_html(_icon_ids[5], _icons[5], "Boting"),
        _create_thinking_html(_icon_ids[6], _icons[6], "Talking with Coworks..."),
        _create_thinking_html(_icon_ids[7], _icons[7], "Fixing..."),
        _create_thinking_html(_icon_ids[8], _icons[8], "Thinking..."),
    ]

    def __init__(self, client: TelegramClient):
        self.client = client
        self.draft_id: Optional[int] = None
        self._update_interval = STREAM_UPDATE_INTERVAL

    async def _cycle_thinking(self, peer) -> None:
        """Pick one random thinking state and keep it until real content arrives."""
        thinking_html = random.choice(self._thinking_htmls)
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
        except Exception as e:
            print(e)

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

        # --- send_file callback ------------------------------------------
        # The closure captures `self` so it can access the Telethon client
        # and event loop, which are set later in _run_async().  The tool
        # handler runs in a worker thread, so we use run_coroutine_threadsafe
        # to schedule the async send_file on the main event loop.
        def _on_send_file(path: str, caption: str) -> None:
            self._do_send_file(path, caption)

        self.engine = BotEngine(
            cfg,
            "telegram",
            connect_mcp=True,
            enable_shell=True,
            auto_confirm=True,
            allowed_shell_commands=allowlist,
            on_send_file=_on_send_file,
        )

        self._api_id_int = api_id_int
        self._api_hash = api_hash
        self._bot_token = bot_token
        self._client: Optional[TelegramClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._current_chat_id: Optional[str] = None

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

            # Capture the event loop for cross-thread file sending
            self._loop = asyncio.get_running_loop()

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
        caption = message.message or ""  # caption is the text accompanying media

        # Track the current chat id so _do_send_file knows where to send
        self._current_chat_id = chat_id

        logger.debug("Message from %s: %s", chat_id, text[:80])

        # Check if the message has media (photo, document, video, audio, voice)
        has_media = bool(message.photo or message.document or message.video
                         or message.voice or message.audio or message.gif
                         or message.sticker or message.video_note)

        reply = self.engine.handle_command(chat_id, user_id, text or caption)
        if reply is None:
            if has_media:
                await self._handle_media_message(event, chat_id, caption)
            else:
                await self._handle_message(event, chat_id, text)
        elif reply:
            await self._send_message(event.chat, reply)

    # -- media handling (receiving files) -----------------------------------

    async def _handle_media_message(self, event, chat_id: str, caption: str) -> None:
        """Download media from the message and pass it to the AI engine."""
        message = event.message
        media_info = self._describe_media(message)
        logger.info("Received media: %s", media_info["summary"])

        # Download the media to MEDIA_DIR
        try:
            file_path = await message.download_media(file=str(MEDIA_DIR))
        except Exception as e:
            logger.error(f"Failed to download media: {e}")
            await self._send_message(event.chat, f"❌ Failed to download media: {e}")
            return

        if not file_path:
            await self._send_message(event.chat, "❌ Could not download the attached media.")
            return

        file_path = Path(file_path)
        content_blocks: List[Dict[str, Any]] = []
        prompt_parts: List[str] = []

        # Build the text prompt describing the file
        prompt_parts.append(f"📎 **File received**: `{file_path.name}`")
        prompt_parts.append(f"- **Path**: `{file_path}`")
        prompt_parts.append(f"- **Size**: {media_info['size_display']}")
        prompt_parts.append(f"- **Type**: {media_info['media_type']}")
        if media_info.get("mime_type"):
            prompt_parts.append(f"- **MIME**: {media_info['mime_type']}")
        if caption:
            prompt_parts.append(f"\n**User instruction**: {caption}")
        else:
            prompt_parts.append("\n*No caption provided. Analyze this file.*")

        # For images, try to inline as base64 for vision models
        is_image = media_info["media_type"] == "image" or (
            file_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        )

        if is_image and file_path.stat().st_size <= _MAX_INLINE_IMAGE_SIZE:
            try:
                img_data = file_path.read_bytes()
                img_b64 = base64.b64encode(img_data).decode("utf-8")
                # Determine MIME type
                suffix = file_path.suffix.lower()
                mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                            ".png": "image/png", ".gif": "image/gif",
                            ".webp": "image/webp"}
                mime_type = mime_map.get(suffix, media_info.get("mime_type", "image/jpeg"))
                content_blocks.append({
                    "type": "image",
                    "media_type": mime_type,
                    "data": img_b64,
                })
                prompt_parts.append("\n*(Image attached for visual analysis)*")
            except Exception as e:
                logger.warning(f"Could not inline image: {e}")
                prompt_parts.append(f"\n*(Image saved at {file_path} — use read_file if needed)*")

        # For text-based files, read the content and include in the prompt
        elif self._is_text_file(file_path, media_info.get("mime_type")):
            try:
                text_content = file_path.read_text(errors="replace")
                if len(text_content) > 30000:
                    text_content = text_content[:30000] + "\n...[truncated]"
                prompt_parts.append(f"\n**File contents:**\n```\n{text_content}\n```")
            except Exception as e:
                logger.warning(f"Could not read text file: {e}")
                prompt_parts.append(f"\n*(File saved at {file_path} — use read_file tool to access)*")

        else:
            prompt_parts.append(f"\n*(File saved at `{file_path}` — use read_file or run_shell_command tools to access it)*")

        # Build the full text block
        full_prompt = "\n".join(prompt_parts)
        content_blocks.insert(0, {"type": "text", "text": full_prompt})

        # Now process through the engine with the content blocks
        is_private = chat_id.isdigit() and int(chat_id) > 0
        if is_private:
            await self._handle_private_chat(event, full_prompt, content_blocks)
        else:
            await self._handle_group_chat(event, full_prompt, content_blocks)

    def _describe_media(self, message) -> Dict[str, Any]:
        """Extract metadata from a Telethon message with media."""
        info: Dict[str, Any] = {"summary": "unknown", "media_type": "file", "mime_type": "", "size_display": "unknown"}

        if message.photo:
            info["media_type"] = "image"
            info["summary"] = "photo"
            info["mime_type"] = "image/jpeg"
            # Try to get the largest photo size
            sizes = message.photo.sizes if hasattr(message.photo, "sizes") else []
            if sizes:
                largest = sizes[-1] if isinstance(sizes, list) else sizes
                if hasattr(largest, "size"):
                    size = largest.size
                    info["size_display"] = f"{size / 1024:.1f} KB"
            return info

        if message.document:
            doc = message.document
            mime_type = doc.mime_type or ""
            info["mime_type"] = mime_type
            size = doc.size or 0
            info["size_display"] = f"{size / (1024*1024):.2f} MB" if size >= 1024*1024 else f"{size / 1024:.1f} KB"

            if mime_type.startswith("image/"):
                info["media_type"] = "image"
            elif mime_type.startswith("video/"):
                info["media_type"] = "video"
            elif mime_type.startswith("audio/"):
                info["media_type"] = "audio"
            else:
                info["media_type"] = "document"

            # Try to get filename from attributes
            for attr in doc.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    info["summary"] = attr.file_name
                    break
            if info["summary"] == "unknown":
                info["summary"] = f"{info['media_type']} ({mime_type or 'unknown'})"
            return info

        if message.video:
            info["media_type"] = "video"
            info["summary"] = "video"
            info["mime_type"] = "video/mp4"
            return info

        if message.voice:
            info["media_type"] = "voice"
            info["summary"] = "voice message"
            info["mime_type"] = "audio/ogg"
            return info

        if message.audio:
            info["media_type"] = "audio"
            info["summary"] = "audio"
            return info

        if message.sticker:
            info["media_type"] = "sticker"
            info["summary"] = "sticker"
            return info

        if message.gif:
            info["media_type"] = "gif"
            info["summary"] = "gif"
            return info

        return info

    def _is_text_file(self, file_path: Path, mime_type: str = "") -> bool:
        """Check if a file is text-based and can be read as text."""
        if mime_type in _TEXT_MIME_TYPES:
            return True
        if file_path.suffix.lower() in _TEXT_EXTENSIONS:
            return True
        # Fallback: try to detect by reading first few bytes
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
            return b"\x00" not in chunk  # binary files usually have null bytes
        except Exception:
            return False

    # -- file sending (AI sends files to user) ------------------------------

    def _do_send_file(self, path: str, caption: str) -> None:
        """
        Called by the send_file tool handler (running in a worker thread).
        Schedules the async file send on the main event loop and blocks
        until it completes.
        """
        if not self._client or not self._loop:
            raise RuntimeError("Telegram client not connected")

        chat_id = self._current_chat_id
        if not chat_id:
            raise RuntimeError("No active chat to send file to")

        file_path = Path(path).expanduser().resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        future = asyncio.run_coroutine_threadsafe(
            self._client.send_file(
                int(chat_id),
                str(file_path),
                caption=caption or None,
            ),
            self._loop,
        )
        # Block until the file is sent (with a timeout)
        try:
            future.result(timeout=60)
        except Exception as e:
            raise RuntimeError(f"Failed to send file: {e}")

    async def _handle_message(self, event, chat_id: str, text: str, content_blocks: Optional[List[Dict[str, Any]]] = None) -> None:
        is_private = chat_id.isdigit() and int(chat_id) > 0
        if is_private:
            await self._handle_private_chat(event, text, content_blocks)
        else:
            await self._handle_group_chat(event, text, content_blocks)

    async def _handle_private_chat(self, event, text: str, content_blocks: Optional[List[Dict[str, Any]]] = None) -> None:
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
                asyncio.run_coroutine_threadsafe(
                    draft_mgr.update_draft(peer, current_text), loop
                )

        final_text = await asyncio.to_thread(
            self.engine.reply_with_log,
            str(event.chat_id),
            text,
            True,
            on_text,
            content_blocks,
        )

        success = await draft_mgr.finish_draft(peer, final_text)
        if not success:
            await self._send_message(peer, final_text)

    async def _handle_group_chat(self, event, text: str, content_blocks: Optional[List[Dict[str, Any]]] = None) -> None:
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
            content_blocks,
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
