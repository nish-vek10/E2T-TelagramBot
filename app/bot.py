import logging
import asyncio
import os
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
STARTUP_PDF = os.getenv("STARTUP_PDF", "").strip()

HELP_EMAIL = os.getenv("HELP_EMAIL", "support@example.com").strip()
TELEGRAM_SUPPORT = os.getenv("TELEGRAM_SUPPORT", "@support").strip()

LEADS_DIR = os.getenv("LEADS_DIR", "./app_data").strip()

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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    text = (
        "Welcome to E2T Copy Trading.\n\n"
        "We will help you get started in a few simple steps.\n\n"
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

    text = (
        "You are almost ready to start copy trading.\n\n"
        "Next steps:\n\n"
        "1) Open your trading account\n"
        "Create your StarTrader live account and complete verification.\n\n"
        "2) Watch the setup video\n"
        "Follow the video to understand how the copy trading setup works.\n\n"
        "3) Choose your copy trader\n"
        "Speak with the E2T team about your goals and risk level so we can help you choose the right copier.\n\n"
        f"Platform: {data.get('platform','')}\n"
        f"Email: {data.get('email','')}\n"
        f"Phone: {data.get('phone','')}\n"
        f"Region: {data.get('region','')}\n\n"
        f"If you have any questions, message {TELEGRAM_SUPPORT} or email {HELP_EMAIL}."
    )

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Open trading account", url=AFFILIATE_LINK)],
            [InlineKeyboardButton("Watch setup video", url=SETUP_VIDEO_LINK)],
        ]
    )

    await query.edit_message_text(text, reply_markup=buttons)
    # Optional: send Startup PDF link after a short delay
    if STARTUP_PDF:
        await asyncio.sleep(3)
        pdf_buttons = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📄 Open Startup PDF", url=STARTUP_PDF)]]
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Here’s the Startup PDF you’ll need:",
            reply_markup=pdf_buttons,
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
