import argparse
import logging
import os
import random
import time
from datetime import date, datetime
from logging.handlers import RotatingFileHandler

import requests
from dotenv import load_dotenv

import notify
from api import recgov, reserveca
from campsite_monitor.checker import check_all, check_connectivity
from campsite_monitor.config import load_config
from campsite_monitor.db import SiteDB
from campsite_monitor.status_server import start_status_server, status
from campsite_monitor.summary import format_summary, get_campground_info
from campsite_monitor.tracker import AvailabilityTracker, FailureTracker, NetworkMonitor

LOG = logging.getLogger(__name__)
_LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "campsite_monitor.log")
_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "campsite_data.db")


def parse_args():
    parser = argparse.ArgumentParser(description="Monitor campsite availability")
    parser.add_argument("--dates", required=True, nargs="+", metavar="CHECKIN:CHECKOUT",
                        help="Date ranges as CHECKIN:CHECKOUT (e.g. 2026-04-17:2026-04-19)")
    parser.add_argument("--interval", type=int, default=300, help="Polling interval in seconds (default: 300)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--no-telegram", action="store_true", help="Disable Telegram notifications")
    parser.add_argument("--port", type=int, default=8080, help="Status page port (default: 8080)")
    parser.add_argument("--config", default="config.yaml", help="Config file path (default: config.yaml)")
    return parser.parse_args()


def setup_logging(verbose):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(level)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = RotatingFileHandler(_LOG_FILE, maxBytes=5_000_000, backupCount=3)
    fh.setFormatter(fmt)
    root.addHandler(fh)


def parse_dates(date_args):
    """Parse date range arguments. Returns list of (checkin, checkout) tuples."""
    date_ranges = []
    for d in date_args:
        try:
            ci, co = d.split(":")
            ci_date, co_date = date.fromisoformat(ci), date.fromisoformat(co)
        except (ValueError, TypeError):
            print(f"Error: invalid date range '{d}' \u2014 expected CHECKIN:CHECKOUT (e.g. 2026-04-17:2026-04-19)")
            raise SystemExit(1)
        if co_date <= ci_date:
            print(f"Error: checkout must be after checkin: {d}")
            raise SystemExit(1)
        date_ranges.append((ci_date, co_date))
    return date_ranges


def check_commands(token, last_update_id):
    """Check for incoming /summary commands. Returns new last_update_id."""
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"offset": last_update_id + 1, "timeout": 0},
            timeout=5,
        )
        if resp.status_code != 200:
            return last_update_id, False
        updates = resp.json().get("result", [])
        summary_requested = False
        for update in updates:
            last_update_id = update["update_id"]
            text = update.get("message", {}).get("text", "")
            if text.strip().startswith("/summary"):
                summary_requested = True
        return last_update_id, summary_requested
    except Exception:
        LOG.debug("Failed to check commands", exc_info=True)
        return last_update_id, False


def main():
    args = parse_args()
    load_dotenv()
    setup_logging(args.verbose)

    date_ranges = parse_dates(args.dates)
    config = load_config(args.config)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    use_telegram = not args.no_telegram and token and chat_id

    db = SiteDB(_DB_PATH)
    tracker = AvailabilityTracker(db=db)
    failure_tracker = FailureTracker()
    network = NetworkMonitor()

    reserveca.discover_all_facilities(config["reserveca"])
    LOG.info("Fetching campground info...")
    cg_info = get_campground_info(config["recgov"], reserveca.CAMPGROUNDS, recgov)
    status["started"] = datetime.now().isoformat(timespec="seconds")
    status["date_ranges"] = [f"{ci} to {co}" for ci, co in date_ranges]
    status["campgrounds"] = cg_info

    start_status_server(args.port)

    if use_telegram:
        dates_str = "\n".join(f"  \u2022 {ci} to {co}" for ci, co in date_ranges)
        cg_str = "\n".join(f"  \u2022 {c['name']} ({c['source']}, {c['sites']} sites)" for c in cg_info)
        startup_msg = (
            "\U0001f3d5 *Campsite monitor started!*\n"
            f"*Dates:*\n{dates_str}\n"
            f"*Campgrounds:*\n{cg_str}"
        )
        notify.send_telegram(token, chat_id, startup_msg)

    checks = 0
    failures = 0
    failed_sources = set()
    summary_sent_today = False
    last_update_id = 0

    # Flush any old messages so we don't process stale /summary commands
    if use_telegram:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"offset": -1, "timeout": 0},
                timeout=5,
            )
            updates = resp.json().get("result", [])
            if updates:
                last_update_id = updates[-1]["update_id"]
        except Exception:
            pass

    while True:
        try:
            net_result = network.check(check_connectivity())
            if net_result == "down_alert":
                if use_telegram:
                    notify.send_telegram(token, chat_id, "\u26a0\ufe0f *Network down* for 5\\+ minutes")
            elif net_result == "recovered":
                if use_telegram:
                    notify.send_telegram(token, chat_id, "\u2705 *Network recovered*")

            if net_result in ("up", "recovered"):
                for checkin, checkout in date_ranges:
                    LOG.info("Checking %s to %s...", checkin, checkout)

                    available, errors = check_all(
                        config["recgov"], reserveca.CAMPGROUNDS,
                        checkin, checkout, recgov, reserveca
                    )

                    db.record_check(checkin, checkout, len(available), errors)
                    checks += 1
                    status["checks"] = checks
                    status["last_check"] = datetime.now().isoformat(timespec="seconds")
                    if errors:
                        failures += 1
                        failed_sources.update(errors)
                    status["failures"] = failures
                    status["failed_sources"] = sorted(failed_sources)

                    # Failure tracking
                    all_names = {cg["name"] for cg in config["recgov"]} | {cg["name"] for cg in reserveca.CAMPGROUNDS}
                    newly_failed, recovered = failure_tracker.update(errors, all_names)
                    for name in newly_failed:
                        if use_telegram:
                            notify.send_telegram(token, chat_id, f"\u26a0\ufe0f *API failure:* {notify.escape_md(name)}\n3 consecutive check failures")
                    for name in recovered:
                        if use_telegram:
                            notify.send_telegram(token, chat_id, f"\u2705 *Recovered:* {notify.escape_md(name)}")

                    # Availability tracking
                    new_sites, gone_sites = tracker.update(available, checkin, checkout)
                    nights = (checkout - checkin).days

                    status["sites_found"] = tracker.sites_found_today
                    status["total_tracked"] = tracker.total_tracked

                    for site in new_sites:
                        status["recent_finds"].append(f"{site['campground']} - {site['site']} ({checkin} to {checkout})")
                        status["recent_finds"] = status["recent_finds"][-50:]

                        msg = notify.format_alert(site["campground"], site["site"], site["url"],
                                                  site.get("park_url"), site.get("site_type"))
                        msg += f"\n{checkin} to {checkout} ({nights} night{'s' if nights != 1 else ''})"
                        LOG.info("NEW: %s - %s (%s to %s)", site["campground"], site["site"], checkin, checkout)
                        if use_telegram:
                            notify.send_telegram(token, chat_id, msg)

                    for site in gone_sites:
                        msg = notify.format_gone(site["campground"], site["site"], checkin, checkout)
                        LOG.info("GONE: %s - %s (%s to %s)", site["campground"], site["site"], checkin, checkout)
                        if use_telegram:
                            notify.send_telegram(token, chat_id, msg)

                # Check for /summary command
                if use_telegram:
                    last_update_id, summary_requested = check_commands(token, last_update_id)
                    if summary_requested:
                        summary = format_summary(checks, failures, failed_sources,
                                                 tracker.sites_found_today, tracker.total_tracked,
                                                 config["recgov"], reserveca.CAMPGROUNDS, notify.escape_md)
                        notify.send_telegram(token, chat_id, summary)

                # Daily summary at noon
                now = datetime.now()
                if now.hour == 12 and not summary_sent_today:
                    summary = format_summary(checks, failures, failed_sources,
                                             tracker.sites_found_today, tracker.total_tracked,
                                             config["recgov"], reserveca.CAMPGROUNDS, notify.escape_md)
                    LOG.info("Daily summary:\n%s", summary)
                    if use_telegram:
                        notify.send_telegram(token, chat_id, summary)
                    checks = 0
                    failures = 0
                    failed_sources.clear()
                    tracker.reset_daily()
                    summary_sent_today = True
                elif now.hour != 12:
                    summary_sent_today = False

        except Exception:
            LOG.exception("Unexpected error in main loop, continuing...")

        if args.once:
            break

        jitter = random.randint(-30, 30)
        sleep_time = max(30, args.interval + jitter)
        LOG.info("Sleeping %ds...", sleep_time)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
