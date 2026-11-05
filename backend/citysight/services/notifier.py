"""Optional Telegram alerts (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID).

Sending never raises: a failed alert is logged and the anomaly stays visible
in the API and the SSE stream.
"""
from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 10


def telegram_enabled(config) -> bool:
    return bool(config.get("TELEGRAM_BOT_TOKEN") and config.get("TELEGRAM_CHAT_ID"))


def send_telegram(config, text: str, photo_jpeg: bytes | None = None) -> bool:
    if not telegram_enabled(config):
        return False
    base = f"https://api.telegram.org/bot{config['TELEGRAM_BOT_TOKEN']}"
    chat_id = config["TELEGRAM_CHAT_ID"]
    try:
        if photo_jpeg:
            res = requests.post(f"{base}/sendPhoto", data={"chat_id": chat_id, "caption": text[:1024]},
                                files={"photo": ("anomali.jpg", photo_jpeg, "image/jpeg")},
                                timeout=TIMEOUT_SECONDS)
        else:
            res = requests.post(f"{base}/sendMessage", json={"chat_id": chat_id, "text": text[:4096]},
                                timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        # The exception text contains the URL, and the URL contains the token.
        log.warning("Telegram alert not sent: %s", exc.__class__.__name__)
        return False
    if not res.ok:
        log.warning("Telegram rejected the alert (%s): %s", res.status_code, res.text[:200])
        return False
    return True
