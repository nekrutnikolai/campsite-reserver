# Campsite Availability Monitor

## Project Overview

A Python tool that polls Recreation.gov and ReserveCalifornia APIs for campsite cancellations and sends Telegram alerts. Runs continuously on a Raspberry Pi via systemd.

## Architecture

- `campsite_monitor.py` — Main entry point: CLI parsing, polling loop, status page server, Telegram commands
- `recgov.py` — Recreation.gov API client (monthly availability endpoint)
- `reserveca.py` — ReserveCalifornia API client (facility discovery + grid availability)
- `notify.py` — Telegram message formatting and sending

## Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v
```

## Testing

All tests use unittest with mocks — no live API calls. Run with:
```bash
python -m pytest tests/ -v
```

## Key Patterns

- API errors propagate from `check_availability()` up to `check_all()`, which catches them per-campground and tracks failures independently
- ReserveCalifornia has dual endpoint URLs as fallbacks
- Availability filtering must check `IsFree` AND exclude `IsWalkin`, `IsBlocked`, `IsReservationDraw`, and `Lock` fields
- ReserveCalifornia facility dict keys are arbitrary — always use `fdata["FacilityId"]`, not the dict key
- Dates: Recreation.gov uses `YYYY-MM-DDT00:00:00.000Z`, ReserveCalifornia uses `MM-DD-YYYY`
- The main loop has a top-level exception guard to survive unexpected errors without losing in-memory state

## Deployment

Target: Raspberry Pi running Raspberry Pi OS, deployed via rsync, managed by systemd (`campsite-monitor.service`). Secrets are in `.env` (never committed).
