from __future__ import annotations

import httpx

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Telegram hard limit is 4096 chars. Use a safety margin for MarkdownV2 escapes.
MAX_LEN = 3900


def _send_one(*, client: httpx.Client, bot_token: str, chat_id: str, text: str) -> None:
    url = TELEGRAM_API.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    r = client.post(url, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"Telegram send failed {r.status_code}: {r.text}")
    data = r.json()
    if not data.get("ok", False):
        raise RuntimeError(f"Telegram send failed: {data}")


def _chunk_text(text: str, max_len: int = MAX_LEN) -> list[str]:
    """
    Split on blank lines first (paragraphs). If still too large, split on lines.
    """
    text = (text or "").strip()
    if len(text) <= max_len:
        return [text]

    # Split by paragraphs
    paras = text.split("\n\n")
    chunks: list[str] = []
    cur = ""

    def push():
        nonlocal cur
        if cur.strip():
            chunks.append(cur.strip())
        cur = ""

    for p in paras:
        p = p.strip()
        if not p:
            continue

        # If a single paragraph is too big, split by lines
        if len(p) > max_len:
            lines = p.splitlines()
            for ln in lines:
                ln = ln.rstrip()
                if not ln:
                    continue
                if not cur:
                    cur = ln
                elif len(cur) + 1 + len(ln) <= max_len:
                    cur += "\n" + ln
                else:
                    push()
                    cur = ln
            push()
            continue

        # Normal paragraph append
        if not cur:
            cur = p
        elif len(cur) + 2 + len(p) <= max_len:
            cur += "\n\n" + p
        else:
            push()
            cur = p

    push()
    return chunks


def send_message(*, bot_token: str, chat_id: str, text: str) -> None:
    chunks = _chunk_text(text, MAX_LEN)

    with httpx.Client(timeout=30) as client:
        for i, chunk in enumerate(chunks, start=1):
            _send_one(client=client, bot_token=bot_token, chat_id=chat_id, text=chunk)
