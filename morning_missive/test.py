# Morning missive test
import asyncio
from telegram import Bot
from telegram.error import TelegramError

BOT_TOKEN = "8415090521:AAG0rGeoPofjB1zBtmDOxVp2l7paYCB5C98"
CHAT_ID   = -1001421848422                                    # ← From your link
THREAD_ID = 110243                                            # ← From your link (the topic/thread)
MESSAGE_TEXT = "Hello! This message goes directly into the specific thread/topic from Nish 😄"
# ────────────────────────────────────────────────

async def main():
    bot = Bot(token=BOT_TOKEN)

    try:
        sent_message = await bot.send_message(
            chat_id=CHAT_ID,
            text=MESSAGE_TEXT,
            message_thread_id=THREAD_ID,   # ← this sends it to the correct topic
        )
        print(f"Message sent successfully!")
        print(f"Message ID: {sent_message.message_id}")
        print(f"In thread: {sent_message.message_thread_id}")
        print(f"To chat: {sent_message.chat_id}")

    except TelegramError as e:
        print(f"Error sending message: {e}")
        if "chat not found" in str(e).lower():
            print("→ Check that the bot is added to the group and has permission to post messages.")
        if "thread not found" in str(e).lower():
            print("→ Double-check the message_thread_id (topic may have been deleted or ID changed).")
        if "forbidden" in str(e).lower():
            print("→ Bot probably doesn't have permission to send messages in that group/thread.")

# Run the async function
if __name__ == "__main__":
    asyncio.run(main())