"""
Telegram bot frontend. Talks to the Bot API directly over HTTPS with plain
`requests` and long polling (getUpdates) -- no python-telegram-bot
dependency needed, which keeps this light for low-bandwidth installs.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Set

import requests

from .. import config as cfgmod
from .common import BotEngine

API_ROOT = "https://api.telegram.org/bot{token}"
MAX_MESSAGE_LEN = 4000  # Telegram's real cap is 4096; leave headroom


class TelegramConfigError(RuntimeError):
    pass


class TelegramBot:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg
        self.bot_cfg = cfg["bots"]["telegram"]
        token = cfgmod.resolve_api_key(self.bot_cfg.get("token_env", "TELEGRAM_BOT_TOKEN"))
        if not token:
            raise TelegramConfigError(
                f"No Telegram bot token found in ${self.bot_cfg.get('token_env', 'TELEGRAM_BOT_TOKEN')}.\n"
                "Run `ai bots setup telegram` first."
            )
        self.base = API_ROOT.format(token=token)
        self.engine = BotEngine(cfg, "telegram")
        self._offset = 0

    # -- thin API wrapper -----------------------------------------------------

    def _call(self, method: str, http_timeout: int = 40, **params: Any) -> Any:
        resp = requests.post(f"{self.base}/{method}", json=params, timeout=http_timeout)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error on {method}: {data}")
        return data["result"]

    def send(self, chat_id: Any, text: str) -> None:
        text = text or "(empty response)"
        for i in range(0, len(text), MAX_MESSAGE_LEN):
            chunk = text[i : i + MAX_MESSAGE_LEN]
            try:
                self._call("sendMessage", chat_id=chat_id, text=chunk)
            except Exception as e:  # noqa: BLE001
                print(f"[telegram] failed to send message: {e}")

    # -- main loop -------------------------------------------------------------

    def run(self) -> None:
        me = self._call("getMe")
        print(f"Telegram bot @{me.get('username')} is running. Press Ctrl+C to stop.")
        allowed_chats: Set[int] = set(self.bot_cfg.get("allowed_chat_ids") or [])

        try:
            while True:
                try:
                    # `timeout` here is Telegram's long-poll wait (seconds,
                    # sent as a JSON param); http_timeout is the local
                    # socket read timeout and must be a bit larger.
                    updates = self._call("getUpdates", http_timeout=40, offset=self._offset, timeout=30)
                except requests.exceptions.RequestException as e:
                    print(f"[telegram] network hiccup, retrying: {e}")
                    time.sleep(3)
                    continue

                for update in updates:
                    self._offset = update["update_id"] + 1
                    try:
                        self._handle_update(update, allowed_chats)
                    except Exception as e:  # noqa: BLE001
                        print(f"[telegram] error handling update: {e}")
        except KeyboardInterrupt:
            print("\n[telegram] stopped.")
        finally:
            self.engine.close()

    def _handle_update(self, update: Dict[str, Any], allowed_chats: Set[int]) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message or "text" not in message:
            return

        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]
        text = message["text"]

        if allowed_chats and chat_id not in allowed_chats:
            return

        try:
            self._call("sendChatAction", chat_id=chat_id, action="typing")
        except Exception:  # noqa: BLE001
            pass

        reply = self.engine.handle_command(str(chat_id), user_id, text)
        if reply is None:
            reply = self.engine.reply(str(chat_id), text)
        self.send(chat_id, reply)
