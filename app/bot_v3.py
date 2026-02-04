# app/bot_v3.py

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional
import warnings
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
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

warnings.filterwarnings(
    "ignore",
    message=r".*per_message=False.*CallbackQueryHandler.*",
)

# ============================================================
# CONFIG (ENV VARS)
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

AFFILIATE_LINK = os.getenv("AFFILIATE_LINK", "").strip()

STARTUP_PDF_FILE = os.getenv("STARTUP_PDF_FILE", "").strip()  # not used now, kept for compatibility
STARTUP_PDF_PREVIEW = os.getenv("STARTUP_PDF_PREVIEW", "").strip()

CEO_VIDEO_NOTE_FILE = os.getenv("CEO_VIDEO_NOTE_FILE", "").strip()

SETUP_VIDEO_FILE = os.getenv("SETUP_VIDEO_FILE", "").strip()
SETUP_VIDEO_PREVIEW = os.getenv("SETUP_VIDEO_PREVIEW", "").strip()
SETUP_VIDEO_LINK = os.getenv("SETUP_VIDEO_LINK", "").strip()  # fallback if no mp4

# Testimonials (you control ordering in code)
TESTIMONIAL_BATCH1 = os.getenv("TESTIMONIAL_BATCH1", "").strip()         # S1..S6
TESTIMONIAL_BATCH2 = os.getenv("TESTIMONIAL_BATCH2", "").strip()         # T7..T9
TESTIMONIAL_PERFORMANCE = os.getenv("TESTIMONIAL_PERFORMANCE", "").strip()  # performance1

HELP_EMAIL = os.getenv("HELP_EMAIL", "support@example.com").strip()
TELEGRAM_SUPPORT = os.getenv("TELEGRAM_SUPPORT", "@educate2trade").strip()

# Where leads.csv will be written by storage.save_lead_csv
LEADS_DIR = os.getenv("LEADS_DIR", "./app_data").strip()

REGIONS = ["UK/EU", "Middle East", "Africa", "Asia", "Americas"]

# ============================================================
# TIMINGS
# ============================================================

DELAY_BEFORE_CEO_VIDEO = 1
DELAY_AFTER_CEO_VIDEO = 4
DELAY_AFTER_GUIDE = 3
DELAY_AFTER_SETUP_VIDEO = 4
DELAY_BEFORE_FINAL_MESSAGE = 4

# Testimonials carousel autoplay behavior
TESTI_ADVANCE_EVERY_SEC = 2
TESTI_IDLE_BEFORE_RESUME_SEC = 3
TESTI_AUTOPLAY_MAX_SEC = 5 * 60       # 5 minutes window per user
TESTI_JOB_NAME = "testi_autoplay"

# ============================================================
# CONVERSATION STATES
# ============================================================

S_START_DECISION, S_EMAIL, S_PHONE, S_REGION, S_REVIEW = range(5)

# ============================================================
# VALIDATION
# ============================================================

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")  # E.164: + and 8-15 digits total

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
log = logging.getLogger("e2t_onboarding_bot")

# Silence APScheduler spam (JobQueue)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)
logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)

# ============================================================
# GENERIC HELPERS
# ============================================================

def _path_exists(p: str) -> bool:
    if not p:
        return False
    try:
        return Path(p).expanduser().exists()
    except Exception:
        return False


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email.strip()))


def normalize_phone(phone: str) -> str:
    return phone.strip().replace(" ", "").replace("-", "")


def is_valid_phone(phone: str) -> bool:
    return bool(PHONE_RE.match(normalize_phone(phone)))


async def _safe_send_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


# ============================================================
# CEO VIDEO NOTE (CIRCULAR)
# ============================================================

async def _send_ceo_video_note(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """
    Telegram shows circular video ONLY if sent as video_note AND
    Telegram accepts it as a valid video_note. Your file must be square-ish
    and within Telegram's constraints.
    """
    if not _path_exists(CEO_VIDEO_NOTE_FILE):
        log.warning("CEO video note file missing: %s", CEO_VIDEO_NOTE_FILE)
        return

    try:
        with open(Path(CEO_VIDEO_NOTE_FILE), "rb") as f:
            await context.bot.send_video_note(chat_id=chat_id, video_note=f)
        return
    except Exception as e:
        log.warning("send_video_note failed, falling back to send_video: %s", e)

    # fallback
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


# ============================================================
# TESTIMONIAL CAROUSEL HELPERS
# ============================================================

def _parse_files(raw: str) -> list[str]:
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def _get_all_testimonial_files() -> list[str]:
    """
    Required order:
      1) Performance (single)
      2) Batch 2
      3) Batch 1
    """
    files: list[str] = []

    perf = _parse_files(TESTIMONIAL_PERFORMANCE)
    if perf:
        files.append(perf[0])

    files += _parse_files(TESTIMONIAL_BATCH2)
    files += _parse_files(TESTIMONIAL_BATCH1)

    out: list[str] = []
    for p in files:
        if _path_exists(p):
            out.append(p)
        else:
            log.warning("Testimonial missing: %s", p)

    return out


def _testi_caption(idx: int, total: int) -> str:
    return (
        f"🚀 Results & Testimonials [{idx + 1}/{total}]"
    )


def _testimonial_nav_keyboard(idx: int, total: int) -> InlineKeyboardMarkup:
    """
    Circular navigation:
      left from 0 -> last
      right from last -> 0
    """
    prev_idx = (idx - 1) % total
    next_idx = (idx + 1) % total

    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("⬅️", callback_data=f"TESTI:{prev_idx}"),
            InlineKeyboardButton(f"{idx + 1}/{total}", callback_data="TESTI:NOOP"),
            InlineKeyboardButton("➡️", callback_data=f"TESTI:{next_idx}"),
        ]]
    )


def _testi_get_state(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> dict:
    """
    Store per-chat carousel state in bot_data so JobQueue callbacks can access it.
    Job callbacks do NOT have user_data, so bot_data is the correct store.
    """
    store = context.application.bot_data.setdefault("testi_state_by_chat", {})
    return store.setdefault(int(chat_id), {})


def _testi_cancel_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.application.bot_data.pop(TESTI_JOB_NAME, None)
    if job:
        try:
            job.schedule_removal()
        except Exception:
            pass


def _testi_schedule_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Ensure ONE global repeating job exists.
    Stored in application.bot_data so multiple users don't create duplicates.
    """
    if context.application.bot_data.get(TESTI_JOB_NAME):
        return

    job = context.job_queue.run_repeating(
        callback=_testimonials_autoplay_tick,
        interval=TESTI_ADVANCE_EVERY_SEC,
        first=TESTI_ADVANCE_EVERY_SEC,
        name=TESTI_JOB_NAME,
    )

    context.application.bot_data[TESTI_JOB_NAME] = job


async def _send_testimonials_carousel(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """
    Sends one photo with ⬅️ ➡️ navigation.
    Starts autoplay, which only advances after idle threshold.
    """
    files = _get_all_testimonial_files()
    if not files:
        log.warning("No testimonial files available.")
        return

    idx = 0
    total = len(files)
    p = files[idx]

    with open(Path(p), "rb") as f:
        msg = await context.bot.send_photo(
            chat_id=chat_id,
            photo=f,
            caption=_testi_caption(idx, total),
            reply_markup=_testimonial_nav_keyboard(idx, total),
        )

    st = _testi_get_state(context, chat_id)
    now = time.time()
    st["testi_files"] = files
    st["testi_idx"] = idx
    st["testi_chat_id"] = chat_id
    st["testi_message_id"] = msg.message_id
    st["testi_last_touch_ts"] = now
    st["testi_started_ts"] = now
    st["testi_autoplay_done"] = False

    _testi_schedule_job(context)


async def _testimonials_autoplay_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Runs every 1s.
    Only advances if user idle >= TESTI_IDLE_BEFORE_RESUME_SEC.
    Uses bot_data state (per chat) because job callbacks have no user_data.
    """
    store = context.application.bot_data.get("testi_state_by_chat") or {}
    if not store:
        return

    # prevent overlapping runs
    if context.application.bot_data.get("_testi_tick_running"):
        return
    context.application.bot_data["_testi_tick_running"] = True

    try:
        now = time.time()

        # iterate all active chats that have an open carousel
        for chat_id, st in list(store.items()):
            files = st.get("testi_files") or []
            if not files:
                continue

            message_id = st.get("testi_message_id")
            if not message_id:
                continue

            last_touch = float(st.get("testi_last_touch_ts") or 0.0)
            if (now - last_touch) < TESTI_IDLE_BEFORE_RESUME_SEC:
                continue  # paused due to recent user interaction

            started = float(st.get("testi_started_ts") or now)
            autoplay_done = bool(st.get("testi_autoplay_done") or False)

            # ---- STOP after 5 minutes (per user/chat) ----
            if not autoplay_done and (now - started) >= TESTI_AUTOPLAY_MAX_SEC:
                # Reset to 1/10 and then mark autoplay done
                st["testi_idx"] = 0
                st["testi_autoplay_done"] = True

                p0 = files[0]
                try:
                    with open(Path(p0), "rb") as f:
                        await context.bot.edit_message_media(
                            chat_id=int(chat_id),
                            message_id=int(message_id),
                            media=InputMediaPhoto(media=f, caption=_testi_caption(0, len(files))),
                        )
                    await context.bot.edit_message_reply_markup(
                        chat_id=int(chat_id),
                        message_id=int(message_id),
                        reply_markup=_testimonial_nav_keyboard(0, len(files)),
                    )
                except Exception as e:
                    # If we can't edit (deleted message etc), just stop tracking this chat
                    log.warning("Autoplay stop/reset failed chat_id=%s err=%s", chat_id, e)
                    try:
                        del store[chat_id]
                    except Exception:
                        pass
                continue

            # If autoplay is done, do nothing further (arrows still work)
            if autoplay_done:
                continue

            # ---- normal auto-advance ----
            total = len(files)
            idx = int(st.get("testi_idx") or 0)
            idx = (idx + 1) % total
            st["testi_idx"] = idx

            p = files[idx]
            try:
                with open(Path(p), "rb") as f:
                    await context.bot.edit_message_media(
                        chat_id=int(chat_id),
                        message_id=int(message_id),
                        media=InputMediaPhoto(media=f, caption=_testi_caption(idx, total)),
                    )
                await context.bot.edit_message_reply_markup(
                    chat_id=int(chat_id),
                    message_id=int(message_id),
                    reply_markup=_testimonial_nav_keyboard(idx, total),
                )
            except Exception as e:
                # Flood control / rate limit: back off for this chat, don't delete state
                msg = str(e)
                if "Flood control exceeded" in msg or "Too Many Requests" in msg:
                    # set last_touch into the future to pause autoplay (cooldown)
                    st["testi_last_touch_ts"] = now + 30
                    log.warning("Autoplay rate-limited for chat_id=%s, pausing 30s. err=%s", chat_id, e)
                    continue

                # Other errors: stop tracking this chat
                log.warning("Autoplay tick failed for chat_id=%s. Removing carousel state. err=%s", chat_id, e)
                try:
                    del store[chat_id]
                except Exception:
                    pass

    finally:
        context.application.bot_data.pop("_testi_tick_running", None)


async def testimonials_nav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Arrow clicks:
      - update image
      - pause autoplay (by updating last_touch timestamp)
    """
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if data == "TESTI:NOOP":
        return
    if not data.startswith("TESTI:"):
        return

    chat_id = query.message.chat_id
    st = _testi_get_state(context, chat_id)

    files = st.get("testi_files") or _get_all_testimonial_files()
    if not files:
        return

    total = len(files)

    try:
        idx = int(data.split("TESTI:", 1)[1])
    except Exception:
        return

    idx = idx % total

    # mark interaction to pause autoplay
    st["testi_last_touch_ts"] = time.time()
    st["testi_files"] = files
    st["testi_idx"] = idx
    st["testi_chat_id"] = chat_id
    st["testi_message_id"] = query.message.message_id

    p = files[idx]

    try:
        with open(Path(p), "rb") as f:
            await query.edit_message_media(
                media=InputMediaPhoto(media=f, caption=_testi_caption(idx, total))
            )
        await query.edit_message_reply_markup(reply_markup=_testimonial_nav_keyboard(idx, total))
    except Exception as e:
        log.warning("Failed to edit testimonial carousel media: %s", e)


# ============================================================
# BROCHURE (ONE IMAGE)
# ============================================================

async def _send_guide_pack(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """
    Brochure-only: sends STARTUP_PDF_PREVIEW image with caption.
    """
    if _path_exists(STARTUP_PDF_PREVIEW):
        try:
            with open(Path(STARTUP_PDF_PREVIEW), "rb") as f:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=f,
                    caption=(
                        "📘 Overview + Performance.\n\n"
                        "This brochure covers strategy performance across multiple years."
                    ),
                )
            return
        except Exception as e:
            log.warning("Failed to send brochure preview: %s", e)

    await _safe_send_message(
        context, chat_id,
        "Brochure image is not configured on the server. Please contact support."
    )


# ============================================================
# SETUP VIDEO
# ============================================================

async def _send_setup_video(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Prefer MP4. Fallback to preview + link."""
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
# FLOW STEPS
# ============================================================

def _reset_details(context: ContextTypes.DEFAULT_TYPE) -> None:
    for k in ("email", "phone", "region"):
        context.user_data.pop(k, None)


async def _run_intro_sequence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        "📊 Welcome to E2T Automated Trading.\n\n"
        "We’ll get you set up in a few steps.\n\n"
        "In a few seconds, you will soon receive the introductory message from our CEO, Bradley Goldberg."
    )

    await asyncio.sleep(DELAY_BEFORE_CEO_VIDEO)
    await _send_ceo_video_note(context, chat_id)

    await _safe_send_message(
        context,
        chat_id,
        "Following this message you will find our results and testimonials from a few of our traders already following the system."
    )
    await asyncio.sleep(2)
    await _send_testimonials_carousel(context, chat_id)

    await asyncio.sleep(DELAY_AFTER_CEO_VIDEO)
    await _send_guide_pack(context, chat_id)

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


# ============================================================
# HANDLERS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    log.info("START received chat_id=%s user_id=%s", update.effective_chat.id, update.effective_user.id)

    context.user_data.clear()
    await _run_intro_sequence(update, context)
    return S_START_DECISION


async def start_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    choice = query.data

    if choice == "PROCEED":
        _reset_details(context)
        await query.edit_message_text("1️⃣ STEP 1:\n\nPlease type your email address.\n(must be valid)")
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
        context.user_data.clear()
        await context.bot.send_message(chat_id=query.message.chat_id, text="Restarting…")

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                "📊 Welcome to E2T Automated Trading. 📊\n\n"
                "We’ll get you set up in a few steps.\n\n"
                "In a few seconds, you will soon receive the introductory message from our CEO, Bradley Goldberg."
            ),
        )

        await asyncio.sleep(DELAY_BEFORE_CEO_VIDEO)
        await _send_ceo_video_note(context, query.message.chat_id)

        await _safe_send_message(
            context,
            query.message.chat_id,
            "Following this message you will find our results and testimonials from a few of our traders already following the system."
        )
        await asyncio.sleep(2)
        await _send_testimonials_carousel(context, query.message.chat_id)

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
        "2️⃣ STEP 2:\n\nPlease enter your mobile number with country code.\n\n"
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
        await query.edit_message_text("No problem.\n\nSTEP 1️⃣:\n\nPlease type your email address again.")
        return S_EMAIL

    if query.data != "DETAILS_OK":
        return S_REVIEW

    user = query.from_user
    csv_path = save_lead_csv(
        base_dir=LEADS_DIR,
        user_id=user.id,
        username=user.username,
        data=context.user_data,
    )
    log.info("Saved lead user_id=%s username=%s -> %s", user.id, user.username, csv_path)

    await query.edit_message_text("✅ Perfect — thanks! Now please watch the setup video below.")
    await _send_setup_video(context, query.message.chat_id)

    await asyncio.sleep(DELAY_AFTER_SETUP_VIDEO)
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

    await asyncio.sleep(DELAY_BEFORE_FINAL_MESSAGE)
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

    context.user_data.clear()
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /start to begin the onboarding process.")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled error: %s", context.error)


# ============================================================
# MAIN
# ============================================================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Set it in your environment or .env file.")

    app = Application.builder().token(BOT_TOKEN).build()

    # IMPORTANT: Add testimonials handler BEFORE conversation handler
    # so arrow clicks always work.
    app.add_handler(CallbackQueryHandler(testimonials_nav, pattern=r"^TESTI:"))
    app.add_error_handler(on_error)

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            S_START_DECISION: [CallbackQueryHandler(start_decision, pattern=r"^(PROCEED|CANCEL|RESTART)$")],
            S_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, take_email)],
            S_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, take_phone)],
            S_REGION: [CallbackQueryHandler(region_choice, pattern=r"^REGION::")],
            S_REVIEW: [CallbackQueryHandler(review_choice, pattern=r"^(EDIT_DETAILS|DETAILS_OK)$")],
        },
        fallbacks=[CommandHandler("help", help_command)],
        allow_reentry=True,
        per_message=False,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("help", help_command))

    log.info("Bot started (polling). Leads dir: %s", LEADS_DIR)
    log.info("CEO_VIDEO_NOTE_FILE exists=%s", _path_exists(CEO_VIDEO_NOTE_FILE))
    log.info("STARTUP_PDF_PREVIEW exists=%s", _path_exists(STARTUP_PDF_PREVIEW))
    log.info("SETUP_VIDEO_FILE exists=%s", _path_exists(SETUP_VIDEO_FILE))
    log.info("SETUP_VIDEO_PREVIEW exists=%s", _path_exists(SETUP_VIDEO_PREVIEW))

    app.run_polling(drop_pending_updates=True, close_loop=False)


if __name__ == "__main__":
    main()
