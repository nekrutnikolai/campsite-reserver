import html
import json
import logging
import os
import string
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

LOG = logging.getLogger(__name__)
_LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "campsite_monitor.log")

# Shared status dict — updated by the main loop, read by the status server
status = {
    "started": None,
    "last_check": None,
    "checks": 0,
    "failures": 0,
    "failed_sources": [],
    "sites_found": 0,
    "total_tracked": 0,
    "date_ranges": [],
    "campgrounds": [],
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
            last_check=last or "\u2014",
            started=status["started"] or "\u2014",
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
