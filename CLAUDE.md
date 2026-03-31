# Campsite Availability Monitor

## Project Overview

A Python tool that polls Recreation.gov and ReserveCalifornia APIs for campsite cancellations and sends Telegram alerts. Runs continuously on a Raspberry Pi via systemd.

## Architecture

```
campsite_monitor/              # Main package (python -m campsite_monitor)
  __main__.py                  # CLI entry point, polling loop, Telegram commands
  checker.py                   # check_all() orchestration across all campgrounds
  config.py                    # load_config() reads config.yaml
  db.py                        # SiteDB — SQLite persistence for site availability
  status_server.py             # Built-in status web page with health indicator
  summary.py                   # format_summary() for Telegram /summary command
  tracker.py                   # AvailabilityTracker, FailureTracker, NetworkMonitor
api/
  recgov.py                    # Recreation.gov API client (monthly availability)
  reserveca.py                 # ReserveCalifornia API client (facility discovery + grid)
notify.py                      # Telegram message formatting and sending
config.yaml                    # Campground configuration (YAML)
```

## Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m campsite_monitor --dates 2026-04-17:2026-04-19 --once --verbose --no-telegram
```

## Testing

All tests use unittest with mocks -- no live API calls. Run with:
```bash
python -m pytest tests/ -v
```

## Key Patterns

- **Config**: Campgrounds are defined in `config.yaml`, loaded by `config.py`. Supports `recgov` and `reserveca` sections with optional `facility_ids` and `filters` for ReserveCalifornia entries.
- **Persistence**: `SiteDB` (SQLite) tracks site availability across restarts. Database file is `campsite_data.db` in the project root.
- **Trackers**: `AvailabilityTracker` manages per-site state (new/gone detection), `FailureTracker` counts consecutive failures per campground, `NetworkMonitor` handles connectivity checks.
- **Error handling**: API errors propagate from `check_availability()` up to `check_all()`, which catches them per-campground and tracks failures independently.
- **ReserveCalifornia**: Has dual endpoint URLs as fallbacks. Facility dict keys are arbitrary -- always use `fdata["FacilityId"]`, not the dict key.
- **Availability filtering**: Must check `IsFree` AND exclude `IsWalkin`, `IsBlocked`, `IsReservationDraw`, and `Lock` fields.
- **Dates**: Recreation.gov uses `YYYY-MM-DDT00:00:00.000Z`, ReserveCalifornia uses `MM-DD-YYYY`.
- **Resilience**: The main loop has a top-level exception guard to survive unexpected errors without losing state.

## Deployment

Target: Raspberry Pi running Raspberry Pi OS, deployed via rsync, managed by systemd (`campsite-monitor.service`). Secrets are in `.env` (never committed). Campground config is in `config.yaml`.
