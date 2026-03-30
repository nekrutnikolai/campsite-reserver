import argparse
import html
import json
import logging
import os
import random
import string
import threading
import time
from datetime import date, datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

import requests

import notify
import recgov
import reserveca

LOG = logging.getLogger(__name__)
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "campsite_monitor.log")


def parse_args():
    parser = argparse.ArgumentParser(description="Monitor campsite availability")
    parser.add_argument("--dates", required=True, nargs="+", metavar="CHECKIN:CHECKOUT",
                        help="Date ranges as CHECKIN:CHECKOUT (e.g. 2026-04-17:2026-04-19)")
    parser.add_argument("--interval", type=int, default=300, help="Polling interval in seconds (default: 300)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--no-telegram", action="store_true", help="Disable Telegram notifications")
    parser.add_argument("--port", type=int, default=8080, help="Status page port (default: 8080)")
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


def check_all(checkin, checkout):
    """Check all campgrounds across both APIs. Returns list of available sites."""
    results = []
    all_campgrounds = [
        (recgov, cg) for cg in recgov.CAMPGROUNDS
    ] + [
        (reserveca, cg) for cg in reserveca.CAMPGROUNDS
    ]

    errors = []
    for module, campground in all_campgrounds:
        try:
            available = module.check_availability(campground, checkin, checkout)
            results.extend(available)
        except Exception:
            LOG.exception("Error checking %s", campground["name"])
            errors.append(campground["name"])

    return results, errors


def format_summary(checks, failures, failed_sources, sites_found, total_tracked):
    all_names = [cg["name"] for cg in recgov.CAMPGROUNDS + reserveca.CAMPGROUNDS]
    lines = ["\U0001f4cb *Daily Summary*"]
    lines.append(f"Checks: {checks}")
    if failures:
        escaped = ", ".join(notify.escape_md(s) for s in sorted(failed_sources))
        lines.append(f"Failed checks: {failures} ({escaped})")
    else:
        lines.append("Errors: none")
    lines.append(f"Sites found today: {sites_found}")
    lines.append(f"Sites found (total): {total_tracked}")
    lines.append("")
    lines.append("*Monitoring:*")
    for name in all_names:
        lines.append(f"  \u2022 {notify.escape_md(name)}")
    return "\n".join(lines)


# Shared status dict updated by the main loop, read by the status server
status = {
    "started": None,
    "last_check": None,
    "checks": 0,
    "failures": 0,
    "failed_sources": [],
    "sites_found": 0,
    "total_tracked": 0,
    "date_ranges": [],
    "campgrounds": [],  # list of {"name", "source", "sites"}

    "recent_finds": [],
}


STATUS_TEMPLATE = string.Template("""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>Campsite Monitor</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 600px; margin: 40px auto; padding: 0 20px; background: #f5f5f5; color: #333; }
  h1 { font-size: 1.4em; }
  .card { background: white; border-radius: 8px; padding: 16px; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .status { display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 0.85em; font-weight: 600; }
  .ok { background: #d4edda; color: #155724; }
  .warn { background: #fff3cd; color: #856404; }
  .down { background: #f8d7da; color: #721c24; }
  .label { color: #888; font-size: 0.85em; }
  .value { font-weight: 600; }
  ul { padding-left: 20px; margin: 8px 0; }
  li { margin: 4px 0; }
  .find { font-size: 0.9em; color: #555; }
  .footer { font-size: 0.8em; color: #aaa; margin-top: 20px; text-align: center; }
  details summary { cursor: pointer; font-weight: 600; font-size: 0.9em; color: #555; }
  .logbox { background: #1e1e1e; color: #d4d4d4; font-family: monospace; font-size: 0.75em; padding: 12px; border-radius: 6px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; margin-top: 8px; }
</style>
</head>
<body>
<h1>Campsite Monitor</h1>
<div class="card">
  <span class="status $health_class">$health_label</span>
  <span class="label" style="margin-left: 8px;">Last check: $last_check</span>
</div>
<div class="card">
  <div><span class="label">Running since:</span> <span class="value">$started</span></div>
  <div><span class="label">Checks:</span> <span class="value">$checks</span></div>
  <div><span class="label">Failures:</span> <span class="value">$failures</span></div>
  $failed_html
  <div><span class="label">Sites found today:</span> <span class="value">$sites_found</span></div>
  <div><span class="label">Sites found (total):</span> <span class="value">$total_tracked</span></div>
</div>
<div class="card">
  <div class="label">Date ranges:</div>
  <ul>$dates_html</ul>
</div>
<div class="card">
  <div class="label">Campgrounds:</div>
  <table style="width:100%; margin-top:8px; font-size:0.9em; border-collapse:collapse;">
    <tr style="text-align:left; border-bottom:1px solid #eee;">
      <th style="padding:4px 8px;">Name</th><th style="padding:4px 8px;">Source</th><th style="padding:4px 8px;">Sites</th>
    </tr>
    $campgrounds_html
  </table>
</div>
$finds_html
<div class="card">
  <details>
    <summary>Recent logs (last 50 lines)</summary>
    <div class="logbox">$logs_html</div>
  </details>
</div>
<div class="footer">Auto-refreshes every 30s</div>
</body>
</html>""")


class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
            return

        now = datetime.now()
        last = status["last_check"]
        if last is None:
            health_class, health_label = "warn", "Starting..."
        else:
            last_dt = datetime.fromisoformat(last)
            age = (now - last_dt).total_seconds()
            if age < 600:
                health_class, health_label = "ok", "Healthy"
            elif age < 1800:
                health_class, health_label = "warn", "Slow"
            else:
                health_class, health_label = "down", "Stale"

        failed_html = ""
        if status["failed_sources"]:
            escaped_sources = ", ".join(html.escape(s) for s in status["failed_sources"])
            failed_html = f'<div><span class="label">Failed sources:</span> {escaped_sources}</div>'

        dates_html = "".join(f"<li>{html.escape(d)}</li>" for d in status["date_ranges"])
        campgrounds_html = "".join(
            f'<tr style="border-bottom:1px solid #f0f0f0;"><td style="padding:4px 8px;">{html.escape(c["name"])}</td><td style="padding:4px 8px;">{html.escape(c["source"])}</td><td style="padding:4px 8px;">{html.escape(str(c["sites"]))}</td></tr>'
            for c in status["campgrounds"]
        ) if isinstance(status["campgrounds"], list) and status["campgrounds"] and isinstance(status["campgrounds"][0], dict) else ""

        finds_html = ""
        if status["recent_finds"]:
            items = "".join(f'<li class="find">{html.escape(f)}</li>' for f in status["recent_finds"][-10:])
            finds_html = f'<div class="card"><div class="label">Recent finds:</div><ul>{items}</ul></div>'

        logs_html = ""
        try:
            with open(_LOG_FILE) as f:
                lines = f.readlines()
                # Filter out noisy DEBUG urllib3 lines
                lines = [l for l in lines if "urllib3" not in l]
                logs_html = "".join(lines[-50:]).replace("<", "&lt;").replace(">", "&gt;")
        except Exception:
            logs_html = "No logs available"

        page = STATUS_TEMPLATE.substitute(
            health_class=health_class,
            health_label=health_label,
            last_check=last or "—",
            started=status["started"] or "—",
            checks=status["checks"],
            failures=status["failures"],
            failed_html=failed_html,
            sites_found=status["sites_found"],
            total_tracked=status["total_tracked"],
            dates_html=dates_html,
            campgrounds_html=campgrounds_html,
            finds_html=finds_html,
            logs_html=logs_html,
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(page.encode())

    def log_message(self, format, *args):
        pass  # suppress access logs


def start_status_server(port):
    server = HTTPServer(("0.0.0.0", port), StatusHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    LOG.info("Status page at http://0.0.0.0:%d", port)


def get_campground_info():
    """Return list of dicts with name, source, and site count for each campground."""
    info = []
    for cg in recgov.CAMPGROUNDS:
        info.append({"name": cg["name"], "source": "Recreation.gov", "sites": "?"})
    for cg in reserveca.CAMPGROUNDS:
        info.append({"name": cg["name"], "source": "ReserveCalifornia", "sites": "?"})

    # Try to fetch actual site counts
    probe_date = date.today().replace(day=1)
    probe_next = (probe_date + timedelta(days=32)).replace(day=1)
    for i, cg in enumerate(recgov.CAMPGROUNDS):
        try:
            resp = requests.get(
                f"https://www.recreation.gov/api/camps/availability/campground/{cg['id']}/month",
                params={"start_date": probe_date.strftime("%Y-%m-%dT00:00:00.000Z")},
                headers={"User-Agent": recgov._UA.random},
                timeout=10,
            )
            if resp.status_code == 200:
                info[i]["sites"] = str(len(resp.json().get("campsites", {})))
        except Exception:
            pass

    offset = len(recgov.CAMPGROUNDS)
    for i, cg in enumerate(reserveca.CAMPGROUNDS):
        try:
            body = {
                "FacilityId": int(cg["facility_id"]),
                "StartDate": probe_date.strftime("%m-%d-%Y"),
                "EndDate": probe_next.strftime("%m-%d-%Y"),
                "IsADA": False, "MinVehicleLength": 0, "WebOnly": True,
                "UnitTypesGroupIds": [], "UnitSort": "SiteNumber", "InSeasonOnly": False,
            }
            for url in reserveca.GRID_URLS:
                try:
                    resp = requests.post(url, json=body, timeout=10)
                    if resp.status_code == 200:
                        info[offset + i]["sites"] = str(len(resp.json().get("Facility", {}).get("Units", {})))
                        break
                except Exception:
                    continue
        except Exception:
            pass

    return info


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

    date_ranges = []
    for d in args.dates:
        ci, co = d.split(":")
        ci_date, co_date = date.fromisoformat(ci), date.fromisoformat(co)
        if co_date <= ci_date:
            print(f"Error: checkout must be after checkin: {d}")
            raise SystemExit(1)
        date_ranges.append((ci_date, co_date))

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    use_telegram = not args.no_telegram and token and chat_id

    reserveca.discover_all_facilities()
    LOG.info("Fetching campground info...")
    cg_info = get_campground_info()
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

    previously_available = {}  # key -> site dict, tracks what was available last cycle
    total_found = set()        # all-time set for counting
    checks = 0
    failures = 0
    failed_sources = set()
    sites_found = 0
    summary_sent_today = False
    last_update_id = 0
    consecutive_failures = {}  # campground name -> count
    alerted_sources = set()    # sources we've already sent a failure alert for

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
        for checkin, checkout in date_ranges:
            LOG.info("Checking availability for %s to %s...", checkin, checkout)

            available, errors = check_all(checkin, checkout)
            checks += 1
            status["checks"] = checks
            status["last_check"] = datetime.now().isoformat(timespec="seconds")
            if errors:
                failures += 1
                failed_sources.update(errors)
            status["failures"] = failures
            status["failed_sources"] = sorted(failed_sources)

            # Track consecutive failures and send alerts
            all_names = {cg["name"] for cg in recgov.CAMPGROUNDS + reserveca.CAMPGROUNDS}
            error_set = set(errors)
            for name in all_names:
                if name in error_set:
                    consecutive_failures[name] = consecutive_failures.get(name, 0) + 1
                    if consecutive_failures[name] == 3 and name not in alerted_sources:
                        alerted_sources.add(name)
                        if use_telegram:
                            notify.send_telegram(token, chat_id,
                                f"\u26a0\ufe0f *API failure:* {notify.escape_md(name)}\n3 consecutive check failures")
                else:
                    if name in alerted_sources:
                        alerted_sources.discard(name)
                        if use_telegram:
                            notify.send_telegram(token, chat_id,
                                f"\u2705 *Recovered:* {notify.escape_md(name)}")
                    consecutive_failures[name] = 0

            nights = (checkout - checkin).days
            now_available = {}
            for site in available:
                key = (site["campground"], site["site"], str(checkin), str(checkout))
                now_available[key] = site

            # Detect NEW sites (in now but not in previously)
            for key, site in now_available.items():
                if key not in previously_available:
                    total_found.add(key)
                    sites_found += 1
                    status["sites_found"] = sites_found
                    status["total_tracked"] = len(total_found)
                    status["recent_finds"].append(f"{site['campground']} - {site['site']} ({checkin} to {checkout})")
                    status["recent_finds"] = status["recent_finds"][-50:]

                    msg = notify.format_alert(site["campground"], site["site"], site["url"], site.get("park_url"))
                    msg += f"\n{checkin} to {checkout} ({nights} night{'s' if nights != 1 else ''})"
                    LOG.info("NEW: %s - %s (%s to %s)", site["campground"], site["site"], checkin, checkout)

                    if use_telegram:
                        notify.send_telegram(token, chat_id, msg)

            # Detect GONE sites (in previously but not in now)
            for key, site in previously_available.items():
                # Only compare keys for the same date range
                if key[2] == str(checkin) and key[3] == str(checkout) and key not in now_available:
                    msg = notify.format_gone(site["campground"], site["site"], checkin, checkout)
                    LOG.info("GONE: %s - %s (%s to %s)", site["campground"], site["site"], checkin, checkout)
                    if use_telegram:
                        notify.send_telegram(token, chat_id, msg)

            # Update previously_available: remove old keys for this date range, add new
            previously_available = {
                k: v for k, v in previously_available.items()
                if not (k[2] == str(checkin) and k[3] == str(checkout))
            }
            previously_available.update(now_available)

        # Check for /summary command
        if use_telegram:
            last_update_id, summary_requested = check_commands(token, last_update_id)
            if summary_requested:
                summary = format_summary(checks, failures, failed_sources, sites_found, len(total_found))
                notify.send_telegram(token, chat_id, summary)

        # Daily summary at noon
        now = datetime.now()
        if now.hour == 12 and not summary_sent_today:
            summary = format_summary(checks, failures, failed_sources, sites_found, len(total_found))
            LOG.info("Daily summary:\n%s", summary)
            if use_telegram:
                notify.send_telegram(token, chat_id, summary)
            checks = 0
            failures = 0
            failed_sources.clear()
            sites_found = 0
            summary_sent_today = True
        elif now.hour != 12:
            summary_sent_today = False

        if args.once:
            break

        jitter = random.randint(-30, 30)
        sleep_time = max(30, args.interval + jitter)
        LOG.info("Sleeping %ds...", sleep_time)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
