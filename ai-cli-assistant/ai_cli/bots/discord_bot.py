"""
Discord bot frontend. Uses discord.py's gateway client (a persistent
WebSocket connection), which is the only realistic way to receive Discord
messages -- unlike Telegram, there's no simple polling HTTP endpoint.

Requires the extra dependency in requirements-bots.txt, and the "Message
Content Intent" toggled on for your bot at
https://discord.com/developers/applications -> your app -> Bot.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Set

from .. import config as cfgmod
from .common import BotEngine

MAX_MESSAGE_LEN = 1900  # Discord's real cap is 2000; leave headroom


class DiscordConfigError(RuntimeError):
    pass


def run_discord_bot(cfg: Dict[str, Any]) -> None:
    try:
        import discord
    except ImportError as e:
        raise DiscordConfigError(
            "The 'discord.py' package is required for the Discord bot.\n"
            "Install with: pip install -r requirements-bots.txt"
        ) from e

    bot_cfg = cfg["bots"]["discord"]
    token = cfgmod.resolve_api_key(bot_cfg.get("token_env", "DISCORD_BOT_TOKEN"))
    if not token:
        raise DiscordConfigError(
            f"No Discord bot token found in ${bot_cfg.get('token_env', 'DISCORD_BOT_TOKEN')}.\n"
            "Run `ai bots setup discord` first."
        )

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    engine = BotEngine(cfg, "discord")
    prefix: str = bot_cfg.get("command_prefix", "!ai ")
    respond_to_mentions: bool = bot_cfg.get("respond_to_mentions", True)
    allowed_guilds: Set[int] = set(bot_cfg.get("allowed_guild_ids") or [])

    @client.event
    async def on_ready() -> None:
        print(f"[discord] logged in as {client.user}. Press Ctrl+C to stop.")

    @client.event
    async def on_message(message: "discord.Message") -> None:
        if message.author.bot:
            return
        if message.guild is not None and allowed_guilds and message.guild.id not in allowed_guilds:
            return

        content = (message.content or "").strip()
        is_dm = message.guild is None
        mentioned = client.user is not None and client.user in message.mentions

        if content.startswith(prefix):
            text = content[len(prefix) :].strip()
        elif is_dm:
            text = content
        elif mentioned and respond_to_mentions:
            text = content
            if client.user is not None:
                text = text.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()
        else:
            return

        if not text:
            return

        chat_id = f"discord:{message.channel.id}"
        user_id = message.author.id

        async with message.channel.typing():
            reply = engine.handle_command(chat_id, user_id, text)
            if reply is None:
                # The AI call is synchronous/blocking -- run it off the
                # event loop thread so the gateway heartbeat doesn't stall.
                reply = await asyncio.to_thread(engine.reply, chat_id, text)

        reply = reply or "(empty response)"
        for i in range(0, len(reply), MAX_MESSAGE_LEN):
            await message.channel.send(reply[i : i + MAX_MESSAGE_LEN])

    try:
        client.run(token)
    finally:
        engine.close()
