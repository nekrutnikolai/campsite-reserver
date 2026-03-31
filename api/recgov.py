import logging
from datetime import date, timedelta

import requests
from fake_useragent import UserAgent

LOG = logging.getLogger(__name__)
_UA = UserAgent(fallback="Mozilla/5.0 (compatible)")

BASE_URL = "https://www.recreation.gov"
AVAILABILITY_URL = BASE_URL + "/api/camps/availability/campground/{id}/month"
BOOKING_URL = BASE_URL + "/camping/campgrounds/{id}"


def check_availability(campground, checkin, checkout):
    """Check a single Recreation.gov campground. Returns list of available sites.
    Each site: {"site": str, "campground": str, "url": str, "park_url": str}"""
    campground_id = campground["id"]
    name = campground["name"]
    url = BOOKING_URL.format(id=campground_id)

    # Collect all dates we need to check
    needed_dates = []
    d = checkin
    while d < checkout:
        needed_dates.append(d)
        d += timedelta(days=1)

    # Determine which months to query
    months = set()
    for d in needed_dates:
        months.add(d.replace(day=1))

    # Fetch availability for each month
    all_availabilities = {}
    headers = {"User-Agent": _UA.random}
    for month_start in sorted(months):
        start_str = month_start.strftime("%Y-%m-%dT00:00:00.000Z")
        resp = requests.get(
            AVAILABILITY_URL.format(id=campground_id),
            params={"start_date": start_str},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        for site_id, site_data in data.get("campsites", {}).items():
            if site_id not in all_availabilities:
                all_availabilities[site_id] = {
                    "site": site_data.get("site", site_id),
                    "availabilities": {},
                }
            all_availabilities[site_id]["availabilities"].update(
                site_data.get("availabilities", {})
            )

    # Check which sites have all needed dates available
    available = []
    for site_id, site_data in all_availabilities.items():
        avail = site_data["availabilities"]
        all_free = True
        for d in needed_dates:
            key = d.strftime("%Y-%m-%dT00:00:00Z")
            if avail.get(key) != "Available":
                all_free = False
                break
        if all_free:
            available.append({
                "site": site_data["site"],
                "campground": name,
                "url": url,
                "park_url": url,
            })

    LOG.debug("%s: %d sites available", name, len(available))
    return available
