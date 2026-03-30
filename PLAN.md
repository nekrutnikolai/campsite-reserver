# Campsite Availability Monitor

Python CLI tool that checks for campsite cancellations and sends Telegram alerts. Runs on a Raspberry Pi.

## Target Dates
- Check-in: 2026-04-17, Check-out: 2026-04-19 (2 nights)
- These should be configurable via CLI args with these defaults

## Campgrounds

### Recreation.gov

| Campground | ID |
|---|---|
| Kirk Creek | 233116 |
| Plaskett Creek | 231959 |

**API:**
```
GET https://www.recreation.gov/api/camps/availability/campground/{id}/month?start_date=2026-04-01T00:00:00.000Z
```
- Returns JSON: `campsites[site_id].availabilities["2026-04-17T00:00:00Z"]` → `"Available"` or `"Reserved"`
- Site is bookable if ALL nights from check-in to night before check-out are `"Available"`
- Needs realistic `User-Agent` header, no auth
- Booking URL: `https://www.recreation.gov/camping/campgrounds/{id}`

### ReserveCalifornia

Only `place_id` is needed — facility sections are auto-discovered at startup via the place API.

| Park | Place ID |
|---|---|
| Julia Pfeiffer Burns SP | 661 |
| Pfeiffer Big Sur SP | 690 |

**APIs** (two base URLs tried in order):
```
# Facility discovery (returns all facility IDs + names + metadata for a park)
POST https://calirdr.usedirect.com/rdr/rdr/search/place        {"PlaceId": 690}
POST https://california-rdr.prod.cali.rd12.recreation-management.tylerapp.com/rdr/search/place

# Availability grid (per-facility, per-date-range)
POST https://calirdr.usedirect.com/rdr/rdr/search/grid
POST https://california-rdr.prod.cali.rd12.recreation-management.tylerapp.com/rdr/search/grid
```
- Place API response includes: facility names, lat/long, park description, highlights, booking restrictions, unit types (tent, RV, premium, ADA), and more
- Facility results cached to `facility_cache.json` (24h TTL, stale cache used as fallback)
- Booking URL: `https://www.reservecalifornia.com/park/{place_id}/{facility_id}`

## Notifications: Telegram

Send via Bot API — just an HTTP GET:
```python
requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
             params={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
```

Token and chat_id loaded from `.env` file. Message should include campground name, site number, and a clickable booking link.

## Core Behavior

1. Check all campgrounds for availability on target dates
2. Track seen sites in memory — only alert on NEW openings
3. Send Telegram message + print to terminal when new site found
4. Wait 5 minutes (+ random jitter ±30s), repeat
5. On startup, send a test Telegram message to confirm it's working

## CLI
```
python campsite_monitor.py [--checkin DATE] [--checkout DATE] [--interval SECONDS] [--once] [--verbose] [--no-telegram]
```

## Requirements
- Python 3.10+
- Dependencies: `requests`, `python-dotenv`
- Graceful error handling — never crash the loop on network/API errors
- Logging to stdout + rotating log file

## Raspberry Pi Deployment

Include a systemd service file (`campsite-monitor.service`) that:
- Starts on boot, restarts on failure
- Runs as user `pi` from `/home/pi/campsite-monitor`
- Uses the project's venv

Include a README with setup steps: clone, create venv, pip install, create .env, test with `--once`, enable systemd service.
