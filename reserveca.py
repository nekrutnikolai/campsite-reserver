import logging
from datetime import date, timedelta

import requests

LOG = logging.getLogger(__name__)

CAMPGROUNDS = [
    {"name": "Julia Pfeiffer Burns SP", "place_id": "661", "facility_id": "518"},
    {"name": "Pfeiffer Big Sur SP", "place_id": "657", "facility_id": "514"},
]

GRID_URLS = [
    "https://calirdr.usedirect.com/rdr/rdr/search/grid",
    "https://california-rdr.prod.cali.rd12.recreation-management.tylerapp.com/rdr/search/grid",
]
BOOKING_URL = "https://www.reservecalifornia.com/Web/#/park/{place_id}/{facility_id}"


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
            needed_dates.append(d.strftime("%m/%d/%Y"))
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
