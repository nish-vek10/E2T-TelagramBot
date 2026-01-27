import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional

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

STARTUP_PDF_FILE = os.getenv("STARTUP_PDF_FILE", "").strip()
STARTUP_PDF_PREVIEW = os.getenv("STARTUP_PDF_PREVIEW", "").strip()

CEO_VIDEO_NOTE_FILE = os.getenv("CEO_VIDEO_NOTE_FILE", "").strip()

SETUP_VIDEO_FILE = os.getenv("SETUP_VIDEO_FILE", "").strip()
SETUP_VIDEO_PREVIEW = os.getenv("SETUP_VIDEO_PREVIEW", "").strip()
SETUP_VIDEO_LINK = os.getenv("SETUP_VIDEO_LINK", "").strip()  # fallback if no mp4

HELP_EMAIL = os.getenv("HELP_EMAIL", "support@example.com").strip()
TELEGRAM_SUPPORT = os.getenv("TELEGRAM_SUPPORT", "@educate2trade").strip()

LEADS_DIR = os.getenv("LEADS_DIR", "./app_data").strip()

REGIONS = ["UK/EU", "Middle East", "Africa", "Asia", "Americas"]

# ---------------- TIMINGS ----------------
DELAY_BEFORE_CEO_VIDEO = 3
DELAY_AFTER_CEO_VIDEO = 5
DELAY_AFTER_GUIDE = 3
DELAY_AFTER_SETUP_VIDEO = 5
DELAY_BEFORE_FINAL_MESSAGE = 5

# ---------------- CONVERSATION STATES ----------------
S_START_DECISION, S_EMAIL, S_PHONE, S_REGION, S_REVIEW = range(5)

# ---------------- VALIDATION ----------------
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")  # E.164: + and 8-15 digits total

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
log = logging.getLogger("e2t_onboarding_bot")


# ============================================================
# Helpers
# ============================================================

def _path_exists(p: str) -> bool:
    if not p:
        return False
    try:
        return Path(p).expanduser().exists()
    except Exception:
        return False


def _kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    """Inline keyboard helper."""
    return InlineKeyboardMarkup([[*rows]])


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email.strip()))


def normalize_phone(phone: str) -> str:
    return phone.strip().replace(" ", "").replace("-", "")


def is_valid_phone(phone: str) -> bool:
    return bool(PHONE_RE.match(normalize_phone(phone)))


async def _safe_send_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str,
                            reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


async def _send_ceo_video_note(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Send CEO circular video note (preferred). Falls back to normal video if needed."""
    if not _path_exists(CEO_VIDEO_NOTE_FILE):
        log.warning("CEO video note file missing: %s", CEO_VIDEO_NOTE_FILE)
        return

    try:
        with open(Path(CEO_VIDEO_NOTE_FILE), "rb") as f:
            await context.bot.send_video_note(chat_id=chat_id, video_note=f)
    except Exception as e:
        log.warning("send_video_note failed, falling back to send_video: %s", e)
        try:
            with open(Path(CEO_VIDEO_NOTE_FILE), "rb") as f:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    caption="Welcome video",
                    supports_streaming=True,
                )
        except Exception as e2:
            log.warning("CEO fallback video also failed: %s", e2)


async def _send_guide_pack(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """
    Telegram cannot attach photo+pdf in one single message.
    Best UX: preview photo with caption, then PDF document with caption.
    """
    # Preview image with caption
    if _path_exists(STARTUP_PDF_PREVIEW):
        try:
            with open(Path(STARTUP_PDF_PREVIEW), "rb") as f:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=f,
                    # caption="📘 Here’s your guide. Please read it before continuing.",
                )
        except Exception as e:
            log.warning("Failed to send STARTUP_PDF_PREVIEW: %s", e)
    else:
        log.warning("Guide preview missing: %s", STARTUP_PDF_PREVIEW)

    # PDF document with caption
    if _path_exists(STARTUP_PDF_FILE):
        try:
            with open(Path(STARTUP_PDF_FILE), "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=Path(STARTUP_PDF_FILE).name,
                    caption="📄 Here is your Copy Trading Guide PDF attached. Please read carefully.",
                )
        except Exception as e:
            log.warning("Failed to send STARTUP_PDF_FILE: %s", e)
            await _safe_send_message(
                context, chat_id,
                "I couldn’t send the PDF file right now. Please contact support."
            )
    else:
        await _safe_send_message(
            context, chat_id,
            "Guide PDF is not configured on the server. Please contact support."
        )


async def _send_setup_video(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Prefer MP4 (plays inside Telegram). Fallback to preview + link."""
    if _path_exists(SETUP_VIDEO_FILE):
        try:
            with open(Path(SETUP_VIDEO_FILE), "rb") as f:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    caption="▶️ Watch this video to set up your trading account.",
                    supports_streaming=True,
                )
            return
        except Exception as e:
            log.warning("Failed to send SETUP_VIDEO_FILE: %s", e)

    # Fallback
    if not SETUP_VIDEO_LINK:
        await _safe_send_message(context, chat_id, "Setup video is not configured. Please contact support.")
        return

    btn = InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Watch setup video", url=SETUP_VIDEO_LINK)]])
    if _path_exists(SETUP_VIDEO_PREVIEW):
        try:
            with open(Path(SETUP_VIDEO_PREVIEW), "rb") as f:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=f,
                    caption="▶️ Setup video (preview)\nTap below to watch:",
                    reply_markup=btn,
                )
            return
        except Exception as e:
            log.warning("Failed to send SETUP_VIDEO_PREVIEW: %s", e)

    await _safe_send_message(context, chat_id, "▶️ Setup video:\nTap below to watch:", reply_markup=btn)


# ============================================================
# Flow Steps
# ============================================================

async def _run_intro_sequence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Your exact start sequence: welcome -> wait -> CEO video -> wait -> guide -> wait -> proceed prompt."""
    chat_id = update.effective_chat.id

    # 1) Welcome message
    await update.message.reply_text(
         "📊Welcome to E2T Copy Trading.📊\n\n"
         "We’ll get you set up in a few steps. \n\n"
         "In a few seconds, you will soon receive our introductory message from our CEO, Bradley Goldberg."
    )

    # 2) wait 5 seconds and then send CEO video note
    await asyncio.sleep(DELAY_BEFORE_CEO_VIDEO)
    await _send_ceo_video_note(context, chat_id)

    # 3) after sending video note, wait 8 seconds
    await asyncio.sleep(DELAY_AFTER_CEO_VIDEO)

    # 4) send guide (caption on preview, then PDF with caption)
    await _send_guide_pack(context, chat_id)

    # 5) wait 3 seconds then proceed/cancel
    await asyncio.sleep(DELAY_AFTER_GUIDE)
    await _safe_send_message(
        context,
        chat_id,
        "Before you proceed we just require some details from you.\n\n"
        "If you wish to continue please click PROCEED below.",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ PROCEED", callback_data="PROCEED")],
                [InlineKeyboardButton("❌ CANCEL", callback_data="CANCEL")],
            ]
        ),
    )


def _reset_details(context: ContextTypes.DEFAULT_TYPE) -> None:
    for k in ("email", "phone", "region"):
        context.user_data.pop(k, None)


# ============================================================
# Handlers
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.info("START received chat_id=%s user_id=%s", update.effective_chat.id, update.effective_user.id)

    context.user_data.clear()
    await _run_intro_sequence(update, context)
    return S_START_DECISION


async def start_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Proceed/Cancel after the guide pack."""
    query = update.callback_query
    await query.answer()

    choice = query.data

    if choice == "PROCEED":
        _reset_details(context)
        await query.edit_message_text("1️⃣ STEP 1: \n\nPlease type your email address. \n(must be valid)")
        return S_EMAIL

    if choice == "CANCEL":
        await query.edit_message_text(
            "Thank you for your time.\n\n"
            "If you wish to start again, click the button below.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔁 START AGAIN", callback_data="RESTART")]]
            ),
        )
        return S_START_DECISION

    if choice == "RESTART":
        # Re-run the whole intro sequence
        context.user_data.clear()
        # We can't use update.message here, so send via bot and then run sequence via a helper
        await context.bot.send_message(chat_id=query.message.chat_id, text="Restarting…")
        # Fake an Update.message isn't possible; so we re-send intro manually:
        # We'll call the same parts using chat_id directly.
        # To keep it simple, we call a minimal version here:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="📊Welcome to E2T Copy Trading.📊\n\n"
                 "We’ll get you set up in a few steps. \n\n"
                 "In a few seconds, you will soon receive our introductory message from our CEO, Bradley Goldberg."
        )
        await asyncio.sleep(DELAY_BEFORE_CEO_VIDEO)
        await _send_ceo_video_note(context, query.message.chat_id)
        await asyncio.sleep(DELAY_AFTER_CEO_VIDEO)
        await _send_guide_pack(context, query.message.chat_id)
        await asyncio.sleep(DELAY_AFTER_GUIDE)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Before you proceed we just require some details from you.\n\nIf you wish to continue please click PROCEED below.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("✅ PROCEED", callback_data="PROCEED")],
                    [InlineKeyboardButton("❌ CANCEL", callback_data="CANCEL")],
                ]
            ),
        )
        return S_START_DECISION

    return S_START_DECISION


async def take_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = (update.message.text or "").strip()

    if not is_valid_email(email):
        await update.message.reply_text(
            "❌ That email doesn’t look valid.\n\n"
            "Please type a valid email like:\n"
            "name@example.com"
        )
        return S_EMAIL

    context.user_data["email"] = email

    await update.message.reply_text(
        "2️⃣ STEP 2: \n\nPlease enter your mobile number with country code.\n\n"
        "Format (required):\n"
        "+447123456789\n"
        "+971501234567\n"
        "+919876543210"
    )
    return S_PHONE


async def take_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone_raw = (update.message.text or "").strip()

    if not is_valid_phone(phone_raw):
        await update.message.reply_text(
            "❌ That phone number is not valid.\n\n"
            "It must include country code and start with +, for example:\n"
            "+447123456789"
        )
        return S_PHONE

    context.user_data["phone"] = normalize_phone(phone_raw)

    buttons = [[InlineKeyboardButton(r, callback_data=f"REGION::{r}")] for r in REGIONS]
    await update.message.reply_text(
        "3️⃣ STEP 3: Select your region:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return S_REGION


async def region_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if not data.startswith("REGION::"):
        await query.edit_message_text("Please choose a valid region.")
        return S_REGION

    region = data.split("REGION::", 1)[1].strip()
    if region not in REGIONS:
        await query.edit_message_text("Please choose a valid region.")
        return S_REGION

    context.user_data["region"] = region

    # 7) Review details with Edit/Confirm buttons (do NOT save yet)
    email = context.user_data.get("email", "")
    phone = context.user_data.get("phone", "")
    region = context.user_data.get("region", "")

    await query.edit_message_text(
        "✅ Done — Please review your details before continuing:\n\n"
        f"EMAIL: {email}\n"
        f"PHONE: {phone}\n"
        f"REGION: {region}\n\n"
        f"If you have any questions, do not hesitate to message {TELEGRAM_SUPPORT}",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✏️ I need to edit my details", callback_data="EDIT_DETAILS")],
                [InlineKeyboardButton("✅ My details are correct", callback_data="DETAILS_OK")],
            ]
        ),
    )
    return S_REVIEW


async def review_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "EDIT_DETAILS":
        _reset_details(context)
        await query.edit_message_text("No problem. \n\n STEP 1️⃣: \n\nPlease type your email address again.")
        return S_EMAIL

    if query.data != "DETAILS_OK":
        return S_REVIEW

    # Only now save lead
    user = query.from_user
    csv_path = save_lead_csv(
        base_dir=LEADS_DIR,
        user_id=user.id,
        username=user.username,
        data=context.user_data,
    )
    log.info("Saved lead user_id=%s username=%s -> %s", user.id, user.username, csv_path)

    # 8) Send setup video with caption
    await query.edit_message_text("✅ Perfect — thanks! Now please watch the setup video below.")
    await _send_setup_video(context, query.message.chat_id)

    # 9) wait 5 seconds then send affiliate message
    await asyncio.sleep(DELAY_AFTER_SETUP_VIDEO)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "Once you understand, click the button below and follow the link to set up your account "
            "for our Copy Trading system."
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Open trading account", url=AFFILIATE_LINK)]]
        ),
    )

    # 10) wait 8 seconds then final instruction
    await asyncio.sleep(DELAY_BEFORE_FINAL_MESSAGE)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "✅ After you’ve opened your account, please confirm with our team.\n\n"
            f"Message {TELEGRAM_SUPPORT} with:\n"
            "• Your full name\n"
            "• The email address you used to open the account\n\n"
            "We’ll then add you to our Premium Copy Trader."
        ),
    )

    context.user_data.clear()
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /start to begin the onboarding process.")


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Set it in your environment or .env file.")

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            S_START_DECISION: [CallbackQueryHandler(start_decision)],
            S_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, take_email)],
            S_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, take_phone)],
            S_REGION: [CallbackQueryHandler(region_choice)],
            S_REVIEW: [CallbackQueryHandler(review_choice)],
        },
        fallbacks=[CommandHandler("help", help_command)],
        allow_reentry=True,
        per_message=False,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_command))

    log.info("Bot started (polling). Leads dir: %s", LEADS_DIR)
    log.info("CEO_VIDEO_NOTE_FILE exists=%s", _path_exists(CEO_VIDEO_NOTE_FILE))
    log.info("STARTUP_PDF_FILE exists=%s", _path_exists(STARTUP_PDF_FILE))
    log.info("STARTUP_PDF_PREVIEW exists=%s", _path_exists(STARTUP_PDF_PREVIEW))
    log.info("SETUP_VIDEO_FILE exists=%s", _path_exists(SETUP_VIDEO_FILE))
    log.info("SETUP_VIDEO_PREVIEW exists=%s", _path_exists(SETUP_VIDEO_PREVIEW))

    app.run_polling(drop_pending_updates=True, close_loop=False)


if __name__ == "__main__":
    main()
