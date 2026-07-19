import asyncio
from telethon import TelegramClient, events, functions, types, helpers
import os

API_ID = 
API_HASH = ""
BOT_TOKEN = ""

STREAM_DELAY = 0.5

RESPONSE = """## AI — Rich Streaming Demo

I'm a helpful assistant with rich formatting and *ai streaming* support.

### What I can do
- Answer questions and explain concepts
- *Draft*, edit, and summarize text
- Write inline code and full code blocks
- Make ==marked==, strikethrough, and spoiler text
- Use [inline links](https://t.me), [mentions](tg://user?id=123456789), and [phones](tel:+123456789)

### Text Formatting
- Headings, lists, tables, code blocks
- Math, quotes, emojis, expandable sections
- Streaming updates with rich formatting

### Auto-detected
Visit https://t.me, contact @username, use #hashtag or $USD, and call +12345678901.

### Footer
_footer text_

---
Thanks for watching the demo!"""

THINKING_VARIANTS = [
    "<tg-thinking><tg-emoji emoji-id=\"5573473356579078196\">🔍</tg-emoji> Searching...</tg-thinking>",
    "<tg-thinking><tg-emoji emoji-id=\"5573473356579078196\">🧠</tg-emoji> Analyzing...</tg-thinking>",
    "<tg-thinking><tg-emoji emoji-id=\"5573473356579078196\">✍️</tg-emoji> Writing...</tg-thinking>",
]

client = TelegramClient("restartable_session", API_ID, API_HASH)


def _new_draft_id():
    return abs(helpers.generate_random_long())


async def _send_draft_html(event, html, draft_id):
    await client(functions.messages.SetTypingRequest(
        peer=event.peer,
        action=types.InputSendMessageRichMessageDraftAction(
            random_id=draft_id,
            rich_message=types.InputRichMessageHTML(html=html),
        ),
    ))


async def _send_draft_md(event, markdown, draft_id):
    await client(functions.messages.SetTypingRequest(
        peer=event.peer,
        action=types.InputSendMessageRichMessageDraftAction(
            random_id=draft_id,
            rich_message=types.InputRichMessageMarkdown(markdown=markdown),
        ),
    ))


async def _thinking_cycle(event, draft_id):
    for html in THINKING_VARIANTS:
        await _send_draft_html(event, html, draft_id)
        await asyncio.sleep(0.8)


async def _stream_draft(event, text, draft_id):
    if not draft_id:
        return

    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    if not blocks:
        return

    for i in range(1, len(blocks) + 1):
        chunk = "\n\n".join(blocks[:i])
        await _send_draft_md(event, chunk, draft_id)
        await asyncio.sleep(STREAM_DELAY)


async def _stream_edit(message, text):
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    if not blocks:
        return

    peer = message.peer
    for i in range(1, len(blocks) + 1):
        chunk = "\n\n".join(blocks[:i])
        try:
            await client(functions.messages.EditMessageRequest(
                peer=peer,
                id=message.id,
                message=chunk,
                rich_message=types.InputRichMessageMarkdown(markdown=chunk),
            ))
            await asyncio.sleep(STREAM_DELAY)
        except Exception:
            await client(functions.messages.EditMessageRequest(
                peer=peer,
                id=message.id,
                message=chunk,
            ))
            await asyncio.sleep(STREAM_DELAY)


async def _send_final_message(event, text):
    await client(functions.messages.SendMessageRequest(
        peer=await event.get_input_chat(),
        message=text[:4000],
        random_id=helpers.generate_random_long(),
        rich_message=types.InputRichMessageMarkdown(markdown=text),
    ))


async def _handle_restart_command(event):
    """Handle /restart command - instructs how to restart the bot"""
    peer = await event.get_input_chat()
    private = peer.is_private
    
    restart_info = """## 🔄 Bot Restart Command

### How to Restart This Bot

The bot will **automatically restart** when its process is terminated. Here are your options:

**Option 1: Manual Restart (Linux/Mac)**
```bash
# The parent process needs to handle restart
# Use a process manager like systemd, docker, or pm2
https://github.com/leg100/TelethonGuide
```

**Option 2: Docker Container**
```yaml
# docker-compose.yml
version: '3'
services:
  ai-bot:
    image: your-bot-image
    restart: always
```

**Option 3: PM2 (Node/Python process manager)**
```bash
# Install pm2 first
pip install pm2

# Start bot with auto-restart
pm2 start telegram_bot.py --name "ai-bot"
pm2 save
```

**Option 4: Telegraph / Cloud Hosting**
- Deploy to Railway, Render, Heroku, or AWS Lambda
- Configure auto-restart settings

---

**Current Session Status**
- Session: `restartable_session`
- Status: 🟢 Active
- Restart triggered: /restart

**Need Help?** Check [Telethon Documentation](https://docs.telethon.dev/)

---
> 💡 **Pro Tip**: For production, use a process supervisor with health checks!
"""
    
    if private:
        draft_id = _new_draft_id()
        await _thinking_cycle(event, draft_id)
        await asyncio.sleep(0.5)
        if draft_id:
            await _stream_draft(event, restart_info, draft_id)
        await _send_final_message(event, restart_info)
    else:
        message = await event.respond("Restart instructions...")
        await _stream_edit(message, restart_info)
        await _send_final_message(event, restart_info)


async def _handle_file_with_caption(event, caption, file):
    peer = await event.get_input_chat()
    private = peer.is_private
    
    filename = file.name or "unknown"
    file_size = file.size or 0
    mime_type = file.mime_type or ""
    file_type = "file"
    
    if mime_type and mime_type.startswith("text/"):
        file_type = "text file"
    elif mime_type in ["image/jpeg", "image/png"]:
        file_type = "image"
    elif mime_type.startswith("video"):
        file_type = "video"
    
    size_mb = file_size / (1024 * 1024)
    size_display = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{file_size / 1024:.2f} KB"
    
    instructions_with_file = f"""## 📄 ``fileName`` = `{filename}` ({size_display})

**instruction** = {caption}

---

## TASK

{caption}

### File Details
- **Name**: `{filename}`
- **Type**: {file_type}
- **Size**: {size_display}
- **MIME**: {mime_type or "unknown"}

---

### AI PROCESSING ---
"""
    
    if private:
        draft_id = _new_draft_id()
        await _thinking_cycle(event, draft_id)
        await asyncio.sleep(0.5)
        if draft_id:
            await _stream_draft(event, instructions_with_file, draft_id)
        await _send_final_message(event, instructions_with_file)
    else:
        message = await event.respond("Processing...")
        await _stream_edit(message, instructions_with_file)
        await _send_final_message(event, instructions_with_file)


async def _handle_text_message(event, text):
    peer = await event.get_input_chat()
    private = peer.is_private
    
    if private:
        draft_id = _new_draft_id()
        await _thinking_cycle(event, draft_id)
        await asyncio.sleep(0.5)
        if draft_id:
            await _stream_draft(event, text, draft_id)
        await _send_final_message(event, text)
    else:
        message = await event.respond("Processing...")
        await _stream_edit(message, text)
        await _send_final_message(event, text)


@client.on(events.NewMessage(pattern=r"^/start"))
async def start_handler(event):
    if event.grouped_id:
        return
    text = "💡 **AI Assistant with File & Media Support**\n\n**Commands**:\n- `/start` - This message\n- `/restart` - Get restart instructions\n- `/upload` - Signal file upload queue\n- `/send <filename>` - Request specific file processing\n- Attach files with captions for auto-processing\n\n**Send**: Files + captions → \"essay.txt: count word 'world'\" 🚀"
    await _handle_text_message(event, text)


@client.on(events.NewMessage(pattern=r"^/restart"))
async def restart_handler(event):
    """Handle /restart command"""
    if event.grouped_id:
        return
    await _handle_restart_command(event)


@client.on(events.NewMessage(pattern=r"^/upload"))
async def upload_handler(event):
    if event.grouped_id:
        return
    text = "/upload: Ready for file upload! Attach a file to process.\n\n**Supported**: .txt, .pdf, .md, .py, .js, .json, images (JPG, PNG, GIF), videos (MP4)"
    await _handle_text_message(event, text)


@client.on(events.NewMessage(pattern=r"^/send (.+)$"))
async def send_handler(event, name):
    if event.grouped_id:
        return
    instr = name
    text = f"/send {instr}: Attach a file named '{instr}' and I'll process it!\n\n**Example**: Send a document and type 'analyze this' as the file name"
    await _handle_text_message(event, text)


@client.on(events.NewMessage(incoming=True))
async def generic_handler(event):
    if event.grouped_id:
        return
    
    document = event.message
    caption = document.text
    file = document.file
    
    if caption and file and file.size:
        await _handle_file_with_caption(event, caption, file)
    elif caption:
        await _handle_text_message(event, caption)
    elif file and file.size:
        filename = file.name or "file"
        size = file.size or 0
        mime_type = file.mime_type or ""
        size_mb = size / (1024 * 1024)
        size_display = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size / 1024:.2f} KB"
        
        text_to_process = f"""## 📄 File Received

**`= {filename} **({size_display})

**MIME Type**: {mime_type or "unknown"}

---

### AI PROCESSING ---

Please analyze:
- **Text files**: Read and process content
- **Images**: Describe/extract text
- **Videos**: Generate description
- **Others**: Let me know!

**How should I handle this file?**"""
        
        peer = await event.get_input_chat()
        private = peer.is_private
        
        if private:
            draft_id = _new_draft_id()
            await _thinking_cycle(event, draft_id)
            await asyncio.sleep(0.5)
            if draft_id:
                await _stream_draft(event, text_to_process, draft_id)
            await _send_final_message(event, text_to_process)
        else:
            message = await event.respond("Processing...")
            await _stream_edit(message, text_to_process)
            await _send_final_message(event, text_to_process)
    else:
        await _handle_text_message(event, document.text)


def main():
    if not API_ID or not API_HASH or not BOT_TOKEN:
        print("Set API_ID, API_HASH, and BOT_TOKEN directly in the script.")
        return

    client.start(bot_token=BOT_TOKEN)
    print("✅ Bot started! Commands: /start /restart /upload /send")
    print("🔄 Type '/restart' in chat to see how to restart the bot")
    client.run_until_disconnected()


if __name__ == "__main__":
    main()
