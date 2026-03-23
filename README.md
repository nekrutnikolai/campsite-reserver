# Campsite Availability Monitor

Polls [Recreation.gov](https://www.recreation.gov) and [ReserveCalifornia](https://www.reservecalifornia.com) for campsite cancellations and sends Telegram alerts. Designed to run on a Raspberry Pi via systemd.

## Features

- Monitors multiple campgrounds across both Recreation.gov and ReserveCalifornia
- Supports multiple date ranges (e.g. 1-night and 2-night stays)
- Telegram alerts when a site opens up
- `/summary` bot command for on-demand status
- Daily summary at noon
- Built-in status web page with health indicator and logs
- Rotating log files (20MB max)

## Quick Start

```bash
git clone <repo-url> && cd campsite-reserver
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit with your Telegram credentials
```

## Telegram Bot Setup

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`
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
python campsite_monitor.py --dates 2024-06-14:2024-06-16 --once --verbose --no-telegram

# Monitor multiple date ranges
python campsite_monitor.py --dates 2024-06-14:2024-06-16 2024-06-15:2024-06-16

# Custom polling interval (seconds, default: 300)
python campsite_monitor.py --dates 2024-06-14:2024-06-16 --interval 120

# Custom status page port (default: 8080)
python campsite_monitor.py --dates 2024-06-14:2024-06-16 --port 9090
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--dates` | Date ranges as `CHECKIN:CHECKOUT` (required, multiple allowed) |
| `--interval` | Polling interval in seconds (default: 300) |
| `--once` | Run a single check and exit |
| `--verbose` | Enable debug logging |
| `--no-telegram` | Disable Telegram notifications |
| `--port` | Status page port (default: 8080) |

### Telegram Commands

| Command | Description |
|---------|-------------|
| `/summary` | Get current stats (checks, errors, sites found) |

## Configuration

### Campgrounds

Edit `recgov.py` and `reserveca.py` to change which campgrounds are monitored.

**Recreation.gov** (`recgov.py`): Find campground IDs from the URL — e.g. `recreation.gov/camping/campgrounds/233116` → ID is `233116`.

**ReserveCalifornia** (`reserveca.py`): Find `place_id` and `facility_id` from the booking URL — e.g. `reservecalifornia.com/Web/#/park/661/518` → place_id `661`, facility_id `518`.

## Raspberry Pi Deployment

```bash
# Copy files to the Pi
rsync -avz --exclude 'venv/' --exclude '__pycache__/' --exclude '.git/' \
  --exclude '.pytest_cache/' --exclude '*.log' \
  ./ pi@<PI_IP>:/home/pi/campsite-monitor/

# On the Pi
cd /home/pi/campsite-monitor
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Edit the service file with your dates
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

## Tests

```bash
python -m pytest tests/ -v
```

## Next Steps

- [ ] Add more campgrounds (Limekiln, Andrew Molera, etc.)
- [ ] Add SMS alerts via Twilio as a backup notification channel
- [ ] Add support for filtering by site type (tent, RV, group)
- [ ] Webhook integration (Slack, Discord)
- [ ] Track price and site attributes in alerts
- [ ] Auto-booking via browser automation (Selenium/Playwright)
