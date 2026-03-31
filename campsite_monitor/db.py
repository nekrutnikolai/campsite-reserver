import json
import logging
import sqlite3
from datetime import datetime

LOG = logging.getLogger(__name__)


class SiteDB:
    """SQLite persistence for found sites and check history."""

    def __init__(self, path="campsite_data.db"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS found_sites (
                id INTEGER PRIMARY KEY,
                campground TEXT NOT NULL,
                site TEXT NOT NULL,
                checkin TEXT NOT NULL,
                checkout TEXT NOT NULL,
                found_at TIMESTAMP NOT NULL,
                gone_at TIMESTAMP,
                url TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_found_sites_lookup
                ON found_sites(campground, site, checkin, checkout);

            CREATE TABLE IF NOT EXISTS check_log (
                id INTEGER PRIMARY KEY,
                checked_at TIMESTAMP NOT NULL,
                checkin TEXT NOT NULL,
                checkout TEXT NOT NULL,
                sites_found INTEGER NOT NULL,
                errors TEXT
            );
        """)
        self.db.commit()

    def record_find(self, campground, site, checkin, checkout, url=""):
        """Record a found site. Returns True if this is new, False if already known (still active)."""
        # Check if this site is currently tracked (found but not gone)
        existing = self.db.execute(
            "SELECT id FROM found_sites WHERE campground=? AND site=? AND checkin=? AND checkout=? AND gone_at IS NULL",
            (campground, site, checkin, checkout)
        ).fetchone()
        if existing:
            return False  # Already known

        self.db.execute(
            "INSERT INTO found_sites (campground, site, checkin, checkout, found_at, url) VALUES (?, ?, ?, ?, ?, ?)",
            (campground, site, checkin, checkout, datetime.now().isoformat(), url)
        )
        self.db.commit()
        return True

    def record_gone(self, campground, site, checkin, checkout):
        """Mark a currently-tracked site as gone."""
        self.db.execute(
            "UPDATE found_sites SET gone_at=? WHERE campground=? AND site=? AND checkin=? AND checkout=? AND gone_at IS NULL",
            (datetime.now().isoformat(), campground, site, checkin, checkout)
        )
        self.db.commit()

    def record_check(self, checkin, checkout, sites_found, errors=None):
        """Log a check cycle."""
        self.db.execute(
            "INSERT INTO check_log (checked_at, checkin, checkout, sites_found, errors) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), str(checkin), str(checkout), sites_found, json.dumps(errors or []))
        )
        self.db.commit()

    def get_recent_finds(self, limit=50):
        """Return recent finds as list of dicts."""
        rows = self.db.execute(
            "SELECT campground, site, checkin, checkout, found_at, gone_at, url FROM found_sites ORDER BY found_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self, days=1):
        """Return stats for last N days."""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        checks = self.db.execute(
            "SELECT COUNT(*) FROM check_log WHERE checked_at > ?", (cutoff,)
        ).fetchone()[0]

        finds = self.db.execute(
            "SELECT COUNT(*) FROM found_sites WHERE found_at > ?", (cutoff,)
        ).fetchone()[0]

        gones = self.db.execute(
            "SELECT COUNT(*) FROM found_sites WHERE gone_at IS NOT NULL AND gone_at > ?", (cutoff,)
        ).fetchone()[0]

        return {"checks": checks, "sites_found": finds, "sites_gone": gones}

    def close(self):
        self.db.close()
