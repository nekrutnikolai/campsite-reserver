import tempfile
import os

import pytest

from campsite_monitor.db import SiteDB


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    sdb = SiteDB(path)
    yield sdb
    sdb.close()
    os.unlink(path)


def test_record_find_new(db):
    result = db.record_find("Kirk Creek", "Site 1", "2026-06-01", "2026-06-03")
    assert result is True


def test_record_find_duplicate(db):
    db.record_find("Kirk Creek", "Site 1", "2026-06-01", "2026-06-03")
    result = db.record_find("Kirk Creek", "Site 1", "2026-06-01", "2026-06-03")
    assert result is False


def test_record_find_after_gone(db):
    db.record_find("Kirk Creek", "Site 1", "2026-06-01", "2026-06-03")
    db.record_gone("Kirk Creek", "Site 1", "2026-06-01", "2026-06-03")
    result = db.record_find("Kirk Creek", "Site 1", "2026-06-01", "2026-06-03")
    assert result is True


def test_record_gone(db):
    db.record_find("Kirk Creek", "Site 1", "2026-06-01", "2026-06-03")
    db.record_gone("Kirk Creek", "Site 1", "2026-06-01", "2026-06-03")
    finds = db.get_recent_finds()
    assert finds[0]["gone_at"] is not None


def test_record_check(db):
    db.record_check("2026-06-01", "2026-06-03", 5, errors=["timeout"])
    rows = db.db.execute("SELECT * FROM check_log").fetchall()
    assert len(rows) == 1
    assert rows[0]["sites_found"] == 5


def test_get_recent_finds(db):
    db.record_find("Kirk Creek", "Site 1", "2026-06-01", "2026-06-03")
    db.record_find("Kirk Creek", "Site 2", "2026-06-01", "2026-06-03")
    db.record_find("Plaskett", "Site 10", "2026-06-02", "2026-06-04")
    finds = db.get_recent_finds()
    assert len(finds) == 3
    # Most recent first
    assert finds[0]["campground"] == "Plaskett"


def test_get_recent_finds_limit(db):
    db.record_find("Kirk Creek", "Site 1", "2026-06-01", "2026-06-03")
    db.record_find("Kirk Creek", "Site 2", "2026-06-01", "2026-06-03")
    db.record_find("Plaskett", "Site 10", "2026-06-02", "2026-06-04")
    finds = db.get_recent_finds(limit=2)
    assert len(finds) == 2


def test_get_stats(db):
    db.record_find("Kirk Creek", "Site 1", "2026-06-01", "2026-06-03")
    db.record_find("Kirk Creek", "Site 2", "2026-06-01", "2026-06-03")
    db.record_gone("Kirk Creek", "Site 1", "2026-06-01", "2026-06-03")
    db.record_check("2026-06-01", "2026-06-03", 2)
    db.record_check("2026-06-01", "2026-06-03", 1)
    stats = db.get_stats(days=1)
    assert stats["checks"] == 2
    assert stats["sites_found"] == 2
    assert stats["sites_gone"] == 1


def test_empty_db_stats(db):
    stats = db.get_stats(days=1)
    assert stats["checks"] == 0
    assert stats["sites_found"] == 0
    assert stats["sites_gone"] == 0
