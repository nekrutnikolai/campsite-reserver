import logging
from datetime import date, timedelta

import requests

LOG = logging.getLogger(__name__)


def format_summary(checks, failures, failed_sources, sites_found, total_tracked,
                   recgov_campgrounds, reserveca_campgrounds, escape_md):
    """Format a daily summary message for Telegram."""
    all_names = [cg["name"] for cg in recgov_campgrounds] + [cg["name"] for cg in reserveca_campgrounds]
    lines = ["\U0001f4cb *Daily Summary*"]
    lines.append(f"Checks: {checks}")
    if failures:
        escaped = ", ".join(escape_md(s) for s in sorted(failed_sources))
        lines.append(f"Failed checks: {failures} ({escaped})")
    else:
        lines.append("Errors: none")
    lines.append(f"Sites found today: {sites_found}")
    lines.append(f"Sites found (total): {total_tracked}")
    lines.append("")
    lines.append("*Monitoring:*")
    for name in all_names:
        lines.append(f"  \u2022 {escape_md(name)}")
    return "\n".join(lines)


def get_campground_info(recgov_campgrounds, reserveca_campgrounds, recgov_mod):
    """Return list of dicts with name, source, and site count for each campground."""
    info = []
    for cg in recgov_campgrounds:
        info.append({"name": cg["name"], "source": "Recreation.gov", "sites": "?"})
    for cg in reserveca_campgrounds:
        info.append({"name": cg["name"], "source": "ReserveCalifornia", "sites": "?"})

    probe_date = date.today().replace(day=1)
    probe_next = (probe_date + timedelta(days=32)).replace(day=1)

    for i, cg in enumerate(recgov_campgrounds):
        try:
            resp = requests.get(
                f"https://www.recreation.gov/api/camps/availability/campground/{cg['id']}/month",
                params={"start_date": probe_date.strftime("%Y-%m-%dT00:00:00.000Z")},
                headers={"User-Agent": recgov_mod._UA.random},
                timeout=10,
            )
            if resp.status_code == 200:
                info[i]["sites"] = str(len(resp.json().get("campsites", {})))
        except Exception:
            pass

    # Import here to avoid circular imports
    from api import reserveca as rca_mod
    offset = len(recgov_campgrounds)
    for i, cg in enumerate(reserveca_campgrounds):
        try:
            body = {
                "FacilityId": int(cg["facility_id"]),
                "StartDate": probe_date.strftime("%m-%d-%Y"),
                "EndDate": probe_next.strftime("%m-%d-%Y"),
                "IsADA": False, "MinVehicleLength": 0, "WebOnly": True,
                "UnitTypesGroupIds": [], "UnitSort": "SiteNumber", "InSeasonOnly": False,
            }
            for url in rca_mod.GRID_URLS:
                try:
                    resp = requests.post(url, json=body, timeout=10)
                    if resp.status_code == 200:
                        info[offset + i]["sites"] = str(len(resp.json().get("Facility", {}).get("Units", {})))
                        break
                except Exception:
                    continue
        except Exception:
            pass

    return info
