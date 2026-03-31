# Campsite Availability Monitor

Polls [Recreation.gov](https://www.recreation.gov) and [ReserveCalifornia](https://www.reservecalifornia.com) for campsite cancellations and sends Telegram alerts. Designed to run on a Raspberry Pi via systemd.

## Features

- Monitors multiple campgrounds across both Recreation.gov and ReserveCalifornia
- YAML configuration file for campground setup
- SQLite persistence (survives restarts)
- Site type filtering (tent, RV, group)
- Supports multiple date ranges (e.g. 1-night and 2-night stays)
- Telegram alerts when a site opens up
- Telegram alerts when a previously-available site disappears ("gone" notifications)
- Dual booking links: direct site link + facility grid page
- `/summary` bot command for on-demand status
- Daily summary at noon
- Built-in status web page with health indicator and logs
- Network pre-check skips cycles during WiFi outages (alerts after 5min sustained downtime)
- Rotating log files (5MB max)

## Quick Start

```bash
git clone <repo-url> && cd campsite-reserver
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit with your Telegram credentials
cp config.yaml config.yaml  # edit with your campgrounds
```

## Telegram Bot Setup

1. Message [@BotFather](https://t.me/BotFather) on Telegram -> `/newbot`
2. Follow the prompts, then copy the bot token
3. Open a chat with your new bot and send any message
4. Get your chat ID (or group chat ID):
   ```bash
   curl https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   Look for `"chat":{"id": ...}` in the response
5. Add both values to `.env`

For group chats: add the bot to the group, send a message in the group, then run the `getUpdates` command above. Group chat IDs are negative numbers.

## Usage

```bash
# Single check, no Telegram (test mode)
python -m campsite_monitor --dates 2024-06-14:2024-06-16 --once --verbose --no-telegram

# Monitor multiple date ranges
python -m campsite_monitor --dates 2024-06-14:2024-06-16 2024-06-15:2024-06-16

# Custom polling interval (seconds, default: 300)
python -m campsite_monitor --dates 2024-06-14:2024-06-16 --interval 120

# Custom status page port (default: 8080)
python -m campsite_monitor --dates 2024-06-14:2024-06-16 --port 9090

# Custom config file
python -m campsite_monitor --dates 2024-06-14:2024-06-16 --config my_config.yaml
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--dates` | Date ranges as `CHECKIN:CHECKOUT` (required, multiple allowed) |
| `--interval` | Polling interval in seconds (default: 300, minimum: 30) |
| `--once` | Run a single check and exit |
| `--verbose` | Enable debug logging |
| `--no-telegram` | Disable Telegram notifications |
| `--port` | Status page port (default: 8080) |
| `--config` | Config file path (default: config.yaml) |

### Telegram Commands

| Command | Description |
|---------|-------------|
| `/summary` | Get current stats (checks, errors, sites found) |

## Configuration

### Campgrounds

Edit `config.yaml` to specify which campgrounds to monitor.

```yaml
recgov:
  - id: "233116"
    name: "Kirk Creek"
  - id: "231959"
    name: "Plaskett Creek"

reserveca:
  - place_id: "661"
    name: "Julia Pfeiffer Burns SP"
  - place_id: "690"
    name: "Pfeiffer Big Sur SP"
```

**Recreation.gov**: Find campground IDs from the URL -- e.g. `recreation.gov/camping/campgrounds/233116` -> ID is `233116`.

**ReserveCalifornia**: Find the `place_id` from the booking URL -- e.g. `reservecalifornia.com/park/690/767` -> place_id is `690`. Facility sections (campground loops) are auto-discovered at startup via the ReserveCalifornia API and cached to `facility_cache.json` (24h TTL).

If auto-discovery breaks, you can pin specific facility IDs:
```yaml
reserveca:
  - place_id: "690"
    name: "Pfeiffer Big Sur SP"
    facility_ids: ["767"]
```

To filter by site type, add a `filters` key:
```yaml
reserveca:
  - place_id: "690"
    name: "Pfeiffer Big Sur SP"
    filters:
      site_type: "tent"  # tent, rv, group
```

### ReserveCalifornia API Reference

The place API (`POST /rdr/search/place` with `{"PlaceId": <id>}`) returns rich data that can be used for future features:

**Park-level fields** (`SelectedPlace`):
| Field | Example | Notes |
|-------|---------|-------|
| `Latitude`, `Longitude` | `36.253`, `-121.781` | Park coordinates |
| `Description` | `"Pfeiffer Big Sur State Park has..."` | Full text description |
| `Url` | `http://www.parks.ca.gov/?page_id=570` | Official park page |
| `ImageUrl` | `https://cali-content.usedirect.com/...` | Park photo |
| `Allhighlights` | `"Hiking<br>Swimming<br>..."` | Activities (HTML-separated) |
| `ParkSize` | `"Medium"` | Size category |
| `TimeZone` | `"America/Los_Angeles"` | |
| `Restrictions.FutureBookingStarts` | `"2026-03-24T00:00:00-07:00"` | When reservations open |
| `Restrictions.FutureBookingEnds` | `"2026-09-22T00:00:00-07:00"` | Booking window end |
| `Restrictions.MaximumStay` | `7` | Max nights per reservation |

**Facility-level fields** (each entry in `SelectedPlace.Facilities`):

Note: the `Facilities` dict is keyed by an arbitrary index, not by `FacilityId`. Always use `fdata["FacilityId"]` from inside each object -- the dict key may differ (e.g. Hearst San Simeon has key `"4"` but `FacilityId: 787`).

| Field | Example | Notes |
|-------|---------|-------|
| `FacilityId`, `Name` | `611`, `"South Camp (sites 1-78)"` | |
| `Latitude`, `Longitude` | `36.2425`, `-121.7743` | Facility-specific coordinates |
| `Category` | `"Campgrounds"` or `"Group Camping"` | Facility type |
| `FacilityAllowWebBooking` | `true` | Whether online booking is enabled |
| `InSeason` | `true`/`false` | Current season status |
| `UnitTypes` | Dict of site types | Contains `Name`, `MaxVehicleLength`, `HasAda`, `AvailableCount` |

**Unit type examples** (nested under each facility):
- `"Campsite"` -- standard sites, `MaxVehicleLength: 32`
- `"Tent Campsite"` -- tent-only
- `"Premium Campsite"` / `"Premium Tent Campsite"` -- premium tier
- `"Hike In Primitive Campsite"` -- walk-in sites
- `HasAda: true` -- ADA accessible sites available

**Grid API (availability) gotchas:**
- Slice keys use ISO datetime format: `"2026-04-18T00:00:00"` (not `"04/18/2026"`)
- `IsFree: true` on a Slice means the site is bookable for that night
- `IsWalkin: true` -- site is walk-in only, cannot be booked online (filter these out)
- `IsBlocked: true` -- site is administratively blocked
- `IsReservationDraw: true` -- site is in a reservation lottery
- `Lock: "2026-..."` -- site is locked by another user mid-checkout (transient)

## Project Structure

```
campsite-reserver/
  campsite_monitor/          # Main package
    __main__.py              # CLI entry point, polling loop, Telegram commands
    checker.py               # Availability checking orchestration
    config.py                # YAML config loading
    db.py                    # SQLite persistence (SiteDB)
    status_server.py         # Built-in status web page
    summary.py               # Summary formatting
    tracker.py               # AvailabilityTracker, FailureTracker, NetworkMonitor
  api/                       # API clients
    recgov.py                # Recreation.gov API
    reserveca.py             # ReserveCalifornia API
  notify.py                  # Telegram message formatting and sending
  config.yaml                # Campground configuration
  .env                       # Telegram credentials (not committed)
```

## Raspberry Pi Deployment

```bash
# Copy files to the Pi
rsync -avz --exclude 'venv/' --exclude '__pycache__/' --exclude '.git/' \
  --exclude '.pytest_cache/' --exclude '*.log' --exclude '.env' \
  ./ pi@<PI_IP>:/home/pi/campsite-monitor/

# On the Pi
cd /home/pi/campsite-monitor
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt  # includes pyyaml

# Edit config and service file
nano config.yaml
nano campsite-monitor.service

# Install and start
sudo cp campsite-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable campsite-monitor
sudo systemctl start campsite-monitor

# View logs
sudo journalctl -u campsite-monitor -f
```

The status page will be available at `http://<PI_IP>:8080`.

### DNS Reliability

If the Pi's DNS is unreliable (transient resolution failures), add public DNS fallbacks:

```bash
echo "static domain_name_servers=192.168.1.1 8.8.8.8 1.1.1.1" | sudo tee -a /etc/dhcpcd.conf
sudo systemctl restart dhcpcd
```

Replace `192.168.1.1` with your router's IP.

### Updating

```bash
# From your dev machine
rsync -avz --exclude 'venv/' --exclude '__pycache__/' --exclude '.git/' \
  --exclude '.pytest_cache/' --exclude '*.log' --exclude '.env' \
  ./ pi@<PI_IP>:/home/pi/campsite-monitor/

# On the Pi
sudo systemctl restart campsite-monitor
```

## Tests

```bash
python -m pytest tests/ -v
```

## Next Steps

- [ ] Show park lat/long and booking-window dates in status page
- [ ] Add SMS alerts via Twilio as a backup notification channel
- [ ] Webhook integration (Slack, Discord)
- [ ] Track price and site attributes in alerts
