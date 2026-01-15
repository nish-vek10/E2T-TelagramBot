import csv
import os
from datetime import datetime
from typing import Dict, Any


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def save_lead_csv(base_dir: str, user_id: int, username: str | None, data: Dict[str, Any]) -> str:
    """
    Append a row to leads.csv with the user’s answers.
    Returns the path to the CSV.
    """
    ensure_dir(base_dir)
    filename = os.path.join(base_dir, "leads.csv")
    file_exists = os.path.exists(filename)

    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(
                ["timestamp", "telegram_id", "telegram_username", "platform", "email", "phone", "region"]
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

    return filename
