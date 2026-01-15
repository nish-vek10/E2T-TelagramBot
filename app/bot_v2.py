import logging
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.storage import save_lead_csv

load_dotenv()

# ---------------- CONFIG (ENV VARS) ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

AFFILIATE_LINK = os.getenv("AFFILIATE_LINK", "").strip()
SETUP_VIDEO_LINK = os.getenv("SETUP_VIDEO_LINK", "").strip()

# Preferred: send actual PDF document so it opens inside Telegram
STARTUP_PDF_FILE = os.getenv("STARTUP_PDF_FILE", "").strip()          # e.g. ./assets/startup_guide.pdf
STARTUP_PDF_PREVIEW = os.getenv("STARTUP_PDF_PREVIEW", "").strip()    # e.g. ./assets/startup_guide_cover.jpg

# Fallback: if you only have a URL (works best if it's a direct .pdf link)
STARTUP_PDF = os.getenv("STARTUP_PDF", "").strip()

# Video preview image (optional)
SETUP_VIDEO_PREVIEW = os.getenv("SETUP_VIDEO_PREVIEW", "").strip()    # e.g. ./assets/setup_video_cover.jpg

HELP_EMAIL = os.getenv("HELP_EMAIL", "support@example.com").strip()
TELEGRAM_SUPPORT = os.getenv("TELEGRAM_SUPPORT", "@support").strip()

LEADS_DIR = os.getenv("LEADS_DIR", "./data").strip()

PLATFORMS = ["MT4", "MT5"]
REGIONS = ["UK/EU", "Middle East", "Africa", "Asia", "Americas"]

P_PLATFORM, P_EMAIL, P_PHONE, P_REGION, P_TERMS = range(5)

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("e2t_onboarding_bot")


def make_keyboard(rows: list[list[str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text, callback_data=text) for text in row] for row in rows]
    )


def _path_exists(p: str) -> bool:
    if not p:
        return False
    try:
        return Path(p).expanduser().exists()
    except Exception:
        return False


async def _send_startup_guide_sequence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    1) Send welcome message
    2) wait 2 seconds
    3) send preview image (if available)
    4) send actual PDF as Telegram document (if available), else send link fallback
    """
    # 1) initial message
    await update.message.reply_text(
        "Welcome to Copy Trading.\n"
        "Here is your guide in the following message."
    )

    # 2) delay
    await asyncio.sleep(2)

    # 3) preview (photo)
    if _path_exists(STARTUP_PDF_PREVIEW):
        try:
            with open(Path(STARTUP_PDF_PREVIEW), "rb") as f:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=f,
                    caption="📌 Startup Guide Preview",
                )
        except Exception as e:
            log.warning("Failed to send STARTUP_PDF_PREVIEW: %s", e)

    # 4) send PDF as document (best for in-app open/save)
    if _path_exists(STARTUP_PDF_FILE):
        try:
            with open(Path(STARTUP_PDF_FILE), "rb") as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=Path(STARTUP_PDF_FILE).name,
                    caption="📄 Startup Guide (open/save inside Telegram)",
                )
            return
        except Exception as e:
            log.warning("Failed to send STARTUP_PDF_FILE as document: %s", e)

    # Fallback: send URL button (not guaranteed in-app)
    if STARTUP_PDF:
        pdf_buttons = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📄 Open Startup PDF", url=STARTUP_PDF)]]
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="📄 Startup guide link:",
            reply_markup=pdf_buttons,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    # Step 0: send guide + preview (before onboarding questions)
    await _send_startup_guide_sequence(update, context)

    # Step 1: choose platform
    text = (
        "Now let’s get you set up.\n\n"
        "Step 1: Choose your trading platform:"
    )
    buttons = [[p] for p in PLATFORMS]
    await update.message.reply_text(text, reply_markup=make_keyboard(buttons))
    return P_PLATFORM


async def platform_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    choice = query.data
    if choice not in PLATFORMS:
        await query.edit_message_text("Please choose a valid platform.")
        return P_PLATFORM

    context.user_data["platform"] = choice

    await query.edit_message_text(
        f"Platform set to: {choice}\n\n"
        "Step 2: Please type your email address."
    )
    return P_EMAIL


async def take_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = (update.message.text or "").strip()

    if "@" not in email or "." not in email:
        await update.message.reply_text("That email does not look valid. Please try again:")
        return P_EMAIL

    context.user_data["email"] = email

    await update.message.reply_text(
        "Step 3: Please enter your mobile phone number with country code.\n\n"
        "Examples:\n"
        "+44 7123 456789\n"
        "+971 50 123 4567\n"
        "+91 98765 43210"
    )
    return P_PHONE


async def take_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = (update.message.text or "").strip()

    if len(phone) < 6:
        await update.message.reply_text("That phone number looks too short. Please try again:")
        return P_PHONE

    context.user_data["phone"] = phone

    buttons = [[r] for r in REGIONS]
    await update.message.reply_text("Step 4: Select your region:", reply_markup=make_keyboard(buttons))
    return P_REGION


async def region_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    region = query.data
    if region not in REGIONS:
        await query.edit_message_text("Please choose a valid region.")
        return P_REGION

    context.user_data["region"] = region

    terms = (
        "Before we continue, please confirm:\n\n"
        "- You understand trading involves risk.\n"
        "- Only trade money you can afford to lose.\n"
        "- Past performance does not guarantee future results.\n\n"
        "Do you agree to proceed?"
    )

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("I agree", callback_data="AGREE")],
            [InlineKeyboardButton("Cancel", callback_data="CANCEL")],
        ]
    )

    await query.edit_message_text(terms, reply_markup=buttons)
    return P_TERMS


async def terms_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    decision = query.data
    user = query.from_user

    if decision == "CANCEL":
        context.user_data.clear()
        await query.edit_message_text("Onboarding cancelled. You can type /start to begin again.")
        return ConversationHandler.END

    # Save the lead
    csv_path = save_lead_csv(
        base_dir=LEADS_DIR,
        user_id=user.id,
        username=user.username,
        data=context.user_data,
    )
    log.info("Saved lead user_id=%s username=%s -> %s", user.id, user.username, csv_path)

    data = context.user_data

    # Confirmation summary
    await query.edit_message_text(
        "✅ Great — you’re almost ready.\n\n"
        f"Platform: {data.get('platform','')}\n"
        f"Email: {data.get('email','')}\n"
        f"Phone: {data.get('phone','')}\n"
        f"Region: {data.get('region','')}\n\n"
        f"If you have any questions, message {TELEGRAM_SUPPORT} or email {HELP_EMAIL}."
    )

    # Send video preview + buttons as a separate message
    # (This lets you attach the preview image and keep the buttons under it)
    video_buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Open trading account", url=AFFILIATE_LINK)],
            [InlineKeyboardButton("▶️ Watch setup video", url=SETUP_VIDEO_LINK)],
        ]
    )

    # Try to send preview image first (optional)
    if _path_exists(SETUP_VIDEO_PREVIEW):
        try:
            with open(Path(SETUP_VIDEO_PREVIEW), "rb") as f:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=f,
                    caption="Setup Video (preview)\nTap below to watch:",
                    reply_markup=video_buttons,
                )
        except Exception as e:
            log.warning("Failed to send SETUP_VIDEO_PREVIEW: %s", e)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="▶️ Setup video:\nTap below to watch:",
                reply_markup=video_buttons,
            )
    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="▶️ Setup video:\nTap below to watch:",
            reply_markup=video_buttons,
        )

    context.user_data.clear()
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /start to begin the copy trading onboarding process.")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Set it in your environment or .env file.")

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            P_PLATFORM: [CallbackQueryHandler(platform_choice)],
            P_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, take_email)],
            P_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, take_phone)],
            P_REGION: [CallbackQueryHandler(region_choice)],
            P_TERMS: [CallbackQueryHandler(terms_choice)],
        },
        fallbacks=[CommandHandler("help", help_command)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_command))

    log.info("Bot started (polling). Leads dir: %s", LEADS_DIR)
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
