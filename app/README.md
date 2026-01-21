# E2T Telegram Onboarding Bot

Telegram onboarding bot for E2T Copy Trading.
Guides users through:
- Welcome message + CEO video note
- Startup guide (preview image + PDF inside Telegram)
- Email & phone collection with validation
- Region selection
- Account setup video
- Affiliate account creation
- Final confirmation instructions

---

## Features
- Telegram-native media (video note, PDF, MP4 video)
- Strict email & phone validation
- CSV lead capture
- Safe environment variable configuration
- Designed for Windows & OVH Linux deployment

---

## Environment Variables (`.env`)

```env
BOT_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxx

AFFILIATE_LINK=https://...

CEO_VIDEO_NOTE_FILE=./assets/ceo_welcome.mp4

STARTUP_PDF_FILE=./assets/startup_guide.pdf
STARTUP_PDF_PREVIEW=./assets/startup_guide_cover.jpg

SETUP_VIDEO_FILE=./assets/setup_video.mp4
SETUP_VIDEO_PREVIEW=./assets/setup_video_cover.jpg
SETUP_VIDEO_LINK=https://youtube.com/...

HELP_EMAIL=support@educate2trade.com
TELEGRAM_SUPPORT=@educate2trade

LEADS_DIR=./data
```

---

## Running the Bot

### Running Locally (`Windows`)
```powershell
cd C:\Users\anish\PycharmProjects\E2T-TelegramBot
.\.venv\Scripts\Activate
python -m app.bot_v3
```

### Running on OVH (`Linux`)
```powershell
cd /opt/e2t-telegram-bot
source .venv/bin/activate
python -m app.bot_v3
```