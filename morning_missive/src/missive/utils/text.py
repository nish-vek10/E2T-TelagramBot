from __future__ import annotations
import textwrap

TELEGRAM_MAX = 4096

def shorten(s: str, width: int = 130) -> str:
    s = (s or "").strip()
    return textwrap.shorten(s, width=width, placeholder="…")

def chunk_telegram(text: str, max_len: int = TELEGRAM_MAX) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts = []
    buf = ""
    for line in text.splitlines(True):
        if len(buf) + len(line) <= max_len:
            buf += line
        else:
            if buf.strip():
                parts.append(buf.strip())
            buf = line
    if buf.strip():
        parts.append(buf.strip())
    return parts
