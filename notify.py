import logging

import requests

LOG = logging.getLogger(__name__)


def escape_md(text):
    """Escape Telegram Markdown special characters."""
    for ch in ('_', '*', '`', '['):
        text = text.replace(ch, '\\' + ch)
    return text


def send_telegram(token, chat_id, message):
    """Send a Telegram message. Returns True on success, never raises."""
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=15,
        )
        if resp.status_code == 200:
            return True
        LOG.warning("Telegram error %d: %s", resp.status_code, resp.text)
        return False
    except Exception:
        LOG.exception("Failed to send Telegram message")
        return False


def format_alert(campground, site, url, park_url=None, site_type=None):
    """Format a Markdown alert message."""
    msg = f"\U0001f3d5 *{escape_md(campground)}* \u2014 Site {escape_md(site)} available!"
    if site_type:
        msg += f"\n{escape_md(site_type)}"
    msg += f"\n[Book now]({url})"
    if park_url:
        msg += f" | [Browse facility]({park_url})"
    return msg


def format_gone(campground, site, checkin, checkout):
    """Format a message for a site that is no longer available."""
    return f"\u274c *{escape_md(campground)}* \u2014 Site {escape_md(site)} no longer available\n{checkin} to {checkout}"
