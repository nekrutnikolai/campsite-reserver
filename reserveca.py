import json
import logging
import os
import time
from datetime import date, timedelta

import requests

LOG = logging.getLogger(__name__)

PARKS = [
    {"name": "Julia Pfeiffer Burns SP", "place_id": "661"},
    {"name": "Pfeiffer Big Sur SP", "place_id": "690"},
]

CAMPGROUNDS = []  # populated at startup by discover_all_facilities()

PLACE_URLS = [
    "https://calirdr.usedirect.com/rdr/rdr/search/place",
    "https://california-rdr.prod.cali.rd12.recreation-management.tylerapp.com/rdr/search/place",
]
GRID_URLS = [
    "https://calirdr.usedirect.com/rdr/rdr/search/grid",
    "https://california-rdr.prod.cali.rd12.recreation-management.tylerapp.com/rdr/search/grid",
]
BOOKING_URL = "https://www.reservecalifornia.com/Web/#/park/{place_id}/{facility_id}"

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "facility_cache.json")
CACHE_MAX_AGE = 86400  # 24 hours


def discover_facilities(place_id):
    """Discover facilities for a park via the place API. Returns list of
    {"facility_id": str, "facility_name": str} dicts."""
    body = {"PlaceId": int(place_id)}
    for url in PLACE_URLS:
        try:
            resp = requests.post(url, json=body, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            facilities = data.get("SelectedPlace", {}).get("Facilities", {})
            return [
                {"facility_id": str(fdata["FacilityId"]), "facility_name": fdata["Name"]}
                for fid, fdata in facilities.items()
            ]
        except Exception:
            continue
    raise ConnectionError(f"All ReserveCalifornia endpoints failed for place {place_id}")


def load_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def discover_all_facilities():
    """Discover facilities for all parks and populate CAMPGROUNDS."""
    global CAMPGROUNDS
    cache = load_cache()
    entries = []

    for park in PARKS:
        place_id = park["place_id"]
        name = park["name"]

        # Manual override — skip discovery
        if "facility_ids" in park:
            for fid in park["facility_ids"]:
                entries.append({"name": name, "place_id": place_id, "facility_id": fid})
            LOG.info("%s: using %d manual facility override(s)", name, len(park["facility_ids"]))
            continue

        # Try fresh cache
        cached = cache.get(place_id)
        if cached and time.time() - cached.get("timestamp", 0) < CACHE_MAX_AGE:
            facilities = cached["facilities"]
            LOG.info("%s: loaded %d facilities from cache", name, len(facilities))
        else:
            # Try API discovery
            try:
                facilities = discover_facilities(place_id)
                cache[place_id] = {"facilities": facilities, "timestamp": time.time()}
                save_cache(cache)
                LOG.info("%s: discovered %d facilities via API", name, len(facilities))
            except Exception:
                # Fall back to stale cache
                if cached:
                    facilities = cached["facilities"]
                    LOG.warning("%s: API failed, using stale cache (%d facilities)", name, len(facilities))
                else:
                    LOG.warning("%s: API failed and no cache available, skipping", name)
                    continue

        for fac in facilities:
            entries.append({
                "name": f"{name} \u2014 {fac['facility_name']}",
                "place_id": place_id,
                "facility_id": fac["facility_id"],
            })

    CAMPGROUNDS = entries
    LOG.info("Total facilities to monitor: %d", len(CAMPGROUNDS))


def check_availability(campground, checkin, checkout):
    """Check a single ReserveCalifornia campground. Returns list of available sites.
    On any error, logs a warning and returns []."""
    try:
        facility_id = campground["facility_id"]
        place_id = campground["place_id"]
        name = campground["name"]

        body = {
            "FacilityId": int(facility_id),
            "StartDate": checkin.strftime("%m-%d-%Y"),
            "EndDate": checkout.strftime("%m-%d-%Y"),
            "IsADA": False,
            "MinVehicleLength": 0,
            "WebOnly": True,
            "UnitTypesGroupIds": [],
            "UnitSort": "SiteNumber",
            "InSeasonOnly": False,
        }

        data = None
        for url_candidate in GRID_URLS:
            try:
                resp = requests.post(url_candidate, json=body, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                LOG.debug("ReserveCalifornia responded via %s", url_candidate)
                break
            except Exception:
                continue
        if data is None:
            raise ConnectionError("All ReserveCalifornia endpoints failed")

        units = data.get("Facility", {}).get("Units", {})
        url = BOOKING_URL.format(place_id=place_id, facility_id=facility_id)

        # Build list of dates we need to check
        needed_dates = []
        d = checkin
        while d < checkout:
            needed_dates.append(d.strftime("%Y-%m-%dT00:00:00"))
            d += timedelta(days=1)

        available = []
        for unit_id, unit in units.items():
            slices = unit.get("Slices", {})
            all_free = all(
                slices.get(date_str, {}).get("IsFree", False)
                for date_str in needed_dates
            )
            if all_free:
                available.append({
                    "site": unit.get("Name", unit_id),
                    "campground": name,
                    "url": url,
                })

        LOG.debug("%s: %d sites available", name, len(available))
        return available

    except Exception:
        LOG.warning("Error checking %s", campground.get("name", campground), exc_info=True)
        return []
