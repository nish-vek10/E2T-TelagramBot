import os
import csv
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# -------------------------------------------------
# CONFIG
# -------------------------------------------------

# 1) PASTE YOUR BOT TOKEN HERE (inside quotes)
BOT_TOKEN = "8503601304:AAGGtOfE0LRAubgPTNam3-8UmHGVojbQSDs"

# 2) LINKS
AFFILIATE_LINK = "https://www.startrader.com/live-account/?affid=NzQ1NzEzNQ==&ibpRebateCode=NzQ1NzEzNVNUMTAyNjk="
SETUP_VIDEO_LINK = "https://youtu.be/GbQOhtKFS6c?si=LMmbqYV-lMnIniwc"

# 3) CONTACT (updated to you)
HELP_EMAIL = "ikjot@educate2trade.com"
TELEGRAM_SUPPORT = "@ikjot21"

# 4) OPTIONS
PLATFORMS = ["MT4", "MT5", "cTrader"]
REGIONS = ["UK/EU", "Middle East", "Africa", "Asia", "Americas"]

# 5) CONVERSATION STATES
P_PLATFORM, P_EMAIL, P_PHONE, P_REGION, P_TERMS = range(5)

# Simple in-memory store during the conversation
USER_STATE = {}  # dict[user_id] = {platform, email, phone, region}


# -------------------------------------------------
# HELPERS
# -------------------------------------------------

def make_keyboard(rows):
    """Create an inline keyboard from rows of button labels."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text, callback_data=text) for text in row] for row in rows]
    )


def save_lead(user_id, username, data):
    """Append a row to leads.csv with the user’s answers."""
    filename = "leads.csv"
    file_exists = os.path.exists(filename)

    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(
                [
                    "timestamp",
                    "telegram_id",
                    "telegram_username",
                    "platform",
                    "email",
                    "phone",
                    "region",
                ]
            )
        writer.writerow(
            [
                datetime.now().isoformat(timespec="seconds"),
                user_id,
                username or "",
                data.get("platform", ""),
                data.get("email", ""),
                data.get("phone", ""),
                data.get("region", ""),
            ]
        )


# -------------------------------------------------
# HANDLERS
# -------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    USER_STATE[user.id] = {}

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
    user = query.from_user
    choice = query.data

    if choice not in PLATFORMS:
        await query.edit_message_text("Please choose a valid platform.")
        return P_PLATFORM

    USER_STATE[user.id]["platform"] = choice

    text = (
        f"Platform set to: {choice}\n\n"
        "Step 2: Please type your email address."
    )

    await query.edit_message_text(text)
    return P_EMAIL


async def take_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    email = update.message.text.strip()

    # Very basic validation
    if "@" not in email or "." not in email:
        await update.message.reply_text("That email does not look valid. Please try again:")
        return P_EMAIL

    USER_STATE[user.id]["email"] = email

    text = (
        "Step 3: Please enter your mobile phone number with country code.\n\n"
        "Examples:\n"
        "+44 7123 456789\n"
        "+971 50 123 4567\n"
        "+91 98765 43210"
    )

    await update.message.reply_text(text)
    return P_PHONE


async def take_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    phone = update.message.text.strip()

    # Light validation: just ensure not ridiculously short
    if len(phone) < 6:
        await update.message.reply_text("That phone number looks too short. Please try again:")
        return P_PHONE

    USER_STATE[user.id]["phone"] = phone

    text = "Step 4: Select your region:"
    buttons = [[r] for r in REGIONS]

    await update.message.reply_text(text, reply_markup=make_keyboard(buttons))
    return P_REGION


async def region_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    region = query.data

    if region not in REGIONS:
        await query.edit_message_text("Please choose a valid region.")
        return P_REGION

    USER_STATE[user.id]["region"] = region

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
    user = query.from_user
    decision = query.data

    data = USER_STATE.get(user.id, {})

    if decision == "CANCEL":
        USER_STATE.pop(user.id, None)
        await query.edit_message_text("Onboarding cancelled. You can type /start to begin again.")
        return ConversationHandler.END

    # Save the lead now that they agreed
    save_lead(user.id, user.username, data)

    text = (
        "You are almost ready to start copy trading.\n\n"
        "Next steps:\n\n"
        "1) Open your trading account\n"
        "Create your StarTrader live account and complete verification.\n\n"
        "2) Watch the setup video\n"
        "Follow the video to understand how the copy trading setup works.\n\n"
        "3) Choose your copy trader\n"
        "Speak with the E2T team about your goals and risk level so we can help you choose the right copier.\n\n"
        f"Platform: {data.get('platform', '')}\n"
        f"Email: {data.get('email', '')}\n"
        f"Phone: {data.get('phone', '')}\n"
        f"Region: {data.get('region', '')}\n\n"
        f"If you have any questions, message {TELEGRAM_SUPPORT} or email {HELP_EMAIL}."
    )

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Open trading account", url=AFFILIATE_LINK)],
            [InlineKeyboardButton("Watch setup video", url=SETUP_VIDEO_LINK)],
        ]
    )

    await query.edit_message_text(text, reply_markup=buttons)
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /start to begin the copy trading onboarding process.")


# -------------------------------------------------
# MAIN
# -------------------------------------------------

def main():
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

    app.run_polling()


if __name__ == "__main__":
    main()


