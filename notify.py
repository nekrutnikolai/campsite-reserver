import logging

import requests

LOG = logging.getLogger(__name__)


def send_telegram(token, chat_id, message):
    """Send a Telegram message. Returns True on success, never raises."""
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
        )
        if resp.status_code == 200:
            return True
        LOG.warning("Telegram error %d: %s", resp.status_code, resp.text)
        return False
    except Exception:
        LOG.exception("Failed to send Telegram message")
        return False


def format_alert(campground, site, url):
    """Format a Markdown alert message."""
    return f"\U0001f3d5 *{campground}* — Site {site} available!\n[Book now]({url})"
