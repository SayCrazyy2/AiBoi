import asyncio from telethon import TelegramClient, 
events, functions, types, helpers API_ID = API_HASH 
= "" BOT_TOKEN = "" STREAM_DELAY = 0.5 RESPONSE = 
"""## AI — Rich Streaming Demo I'm a helpful 
assistant with **rich formatting** and *ai 
streaming* support.
### What I can do
- **Answer** questions and explain concepts - 
*Draft*, edit, and summarize text - `Write inline 
code` and full code blocks - Make ==marked==, 
~~strikethrough~~, and ||spoiler|| text - Use 
[inline links](https://t.me), 
[mentions](tg://user?id=123456789), 
[emails](mailto:hi@example.com), and 
[phones](tel:+123456789)
### Task list
- [x] Headings - [x] Lists - [ ] Tables - [x] 
Streaming
### Code example
```python print("Hello, rich messages!") ```
### Math
Inline: $x^2 + y^2 = z^2$ Block: $$E = mc^2$$
### Quote
> A blockquote with **formatting**.
>> Nested quote with more details.
### Table
| Feature | Status | Priority |
|:--------|:------:|---------:|
| Rich text | ✅ | High | Streaming | ✅ | High | 
| Tables | ✅ | Medium |
### Custom emoji
![✨](tg://emoji?id=5573473356579078196)
### Expandable
<details> <summary>Click to see more</summary> 
Hidden content with **bold** and `code`. </details>
### Auto-detected
Visit https://t.me, contact @username, use #hashtag 
or $USD, and call +12345678901.
### Footer
_footer text_ --- Thanks for watching the demo!""" 
THINKING_VARIANTS = [
    "<tg-thinking><tg-emoji 
    emoji-id=\"5573473356579078196\">🔍</tg-emoji> 
    Searching...</tg-thinking>", 
    "<tg-thinking><tg-emoji 
    emoji-id=\"5573473356579078196\">🧠</tg-emoji> 
    Analyzing...</tg-thinking>", 
    "<tg-thinking><tg-emoji 
    emoji-id=\"5573473356579078196\">✍️</tg-emoji> 
    Writing...</tg-thinking>",
] client = TelegramClient("test_stream_session", 
API_ID, API_HASH) def _new_draft_id():
    return abs(helpers.generate_random_long()) async 
def _send_draft_html(event, html, draft_id):
    await 
    client(functions.messages.SetTypingRequest(
        peer=event.chat_id, 
        action=types.InputSendMessageRichMessageDraftAction(
            random_id=draft_id, 
            rich_message=types.InputRichMessageHTML(html=html),
        ), )) async def _send_draft_md(event, 
markdown, draft_id):
    await 
    client(functions.messages.SetTypingRequest(
        peer=event.chat_id, 
        action=types.InputSendMessageRichMessageDraftAction(
            random_id=draft_id, 
            rich_message=types.InputRichMessageMarkdown(markdown=markdown),
        ), )) async def _thinking_cycle(event, 
draft_id):
    for html in THINKING_VARIANTS: await 
        _send_draft_html(event, html, draft_id) 
        await asyncio.sleep(0.8)
async def _stream_draft(event, text, draft_id): if 
    not draft_id:
        return blocks = [b.strip() for b in 
    text.split("\n\n") if b.strip()] if not blocks:
        return for i in range(1, len(blocks) + 1): 
        chunk = "\n\n".join(blocks[:i]) await 
        _send_draft_md(event, chunk, draft_id) await 
        asyncio.sleep(STREAM_DELAY)
async def _stream_edit(message, text): blocks = 
    [b.strip() for b in text.split("\n\n") if 
    b.strip()] if not blocks:
        return peer = await message.get_input_chat() 
    for i in range(1, len(blocks) + 1):
        chunk = "\n\n".join(blocks[:i]) await 
        client(functions.messages.EditMessageRequest(
            peer=peer, id=message.id, 
            message=chunk[:4000], 
            rich_message=types.InputRichMessageMarkdown(markdown=chunk),
        )) await asyncio.sleep(STREAM_DELAY) async 
def _send_final_message(event, text):
    await 
    client(functions.messages.SendMessageRequest(
        peer=await event.get_input_chat(), 
        message=text[:4000], 
        random_id=helpers.generate_random_long(), 
        rich_message=types.InputRichMessageMarkdown(markdown=text),
    )) async def _edit_final_message(message, text): 
    await 
    client(functions.messages.EditMessageRequest(
        peer=await message.get_input_chat(), 
        id=message.id, message=text[:4000], 
        rich_message=types.InputRichMessageMarkdown(markdown=text),
    )) async def _respond(event, text): private = 
    event.is_private if private:
        message = None draft_id = _new_draft_id() 
        await _thinking_cycle(event, draft_id)
    else: message = await 
        event.respond("`Thinking...`") draft_id = 
        None
    await asyncio.sleep(0.5) if private: if 
        draft_id:
            await _stream_draft(event, text, 
            draft_id)
        await _send_final_message(event, text) else: 
        await _stream_edit(message, text) await 
        _edit_final_message(message, text)
@client.on(events.NewMessage(pattern=r"^/start")) 
async def start_handler(event):
    if event.grouped_id: return await 
    _respond(event, RESPONSE)
def main(): if not API_ID or not API_HASH or not 
    BOT_TOKEN:
        print("Set API_ID, API_HASH, and BOT_TOKEN 
        directly in the script.") return
    client.start(bot_token=BOT_TOKEN) print("Bot 
    started. Send /start in a private chat.") 
    client.run_until_disconnected()
if __name__ == "__main__": main()
